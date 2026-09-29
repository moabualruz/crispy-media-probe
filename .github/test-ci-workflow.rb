require "fileutils"
require "open3"
require "tmpdir"
require "yaml"

workflow = YAML.safe_load(File.read(".github/workflows/ci.yml"), aliases: false)
release = YAML.safe_load(File.read(".github/workflows/release.yml"), aliases: false)
jobs = workflow.fetch("jobs")
steps = jobs.values.flat_map { |job| job.fetch("steps", []) }
def uses_ruby_setup?(reference)
  reference.to_s.start_with?("ruby/setup-ruby")
end
abort "Ruby setup guard missed non-v1 references" unless uses_ruby_setup?("ruby/setup-ruby@v2") && uses_ruby_setup?("ruby/setup-ruby") && !uses_ruby_setup?("actions/checkout@v4")
ruby_setup = steps.find { |step| uses_ruby_setup?(step["uses"]) }
abort "CI must use the runner-provisioned Ruby runtime" if ruby_setup
checkouts = steps.select { |step| step["uses"] == "actions/checkout@v4" }

abort "expected one checkout route" unless checkouts.length == 1
checkout = checkouts.first
expected_condition = "github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name != github.repository"
abort "checkout route changed" unless checkout["if"] == expected_condition
abort "checkout credentials must not be persisted" unless checkout.dig("with", "persist-credentials") == false
abort "fork checkout must be pinned to the event SHA" unless checkout.dig("with", "ref") == "${{ github.sha }}"
concurrency = workflow.fetch("concurrency")
abort "CI concurrency group must be PR scoped" unless concurrency.fetch("group") == "crispy-media-probe-pr-${{ github.event.pull_request.number || github.ref }}"
abort "required CI jobs must not be self-cancelled" unless concurrency.fetch("cancel-in-progress") == false
abort "CI must not use cancellation-unsafe always() conditions" if steps.any? { |step| step["if"].to_s.include?("always()") }

release_steps = release.fetch("jobs").fetch("release-check").fetch("steps")
release_checkout = release_steps.find { |step| step["uses"] == "actions/checkout@v4" }
abort "release checkout route missing" unless release_checkout
abort "release checkout credentials must not be persisted" unless release_checkout.dig("with", "persist-credentials") == false

source_jobs = jobs.reject { |name, _job| name == "required" }
source_checks = source_jobs.values.map do |job|
  job.fetch("steps").find { |step| step["name"] == "verify brokered PR source" }
end
abort "each source CI job must verify the brokered PR source" unless source_checks.length == source_jobs.length && source_checks.none?(&:nil?)
source_checks.each do |step|
abort "source check must be limited to same-repo PRs" unless step["if"] == "github.event_name == 'pull_request' && github.event.pull_request.head.repo.full_name == github.repository"
abort "source check must require the brokered workspace symlink" unless step.fetch("run").include?("[ ! -L \"$GITHUB_WORKSPACE\" ]")
abort "source check must compare the worktree root and HEAD to GITHUB_SHA" unless step.fetch("run").include?("git -C \"$workspace\" rev-parse --show-toplevel") && step.fetch("run").include?("git -C \"$workspace\" rev-parse HEAD") && step.fetch("run").include?('[ "$actual_sha" != "$GITHUB_SHA" ]')
end

archive = steps.find { |step| step["name"] == "archive checked out source for hosted jobs" }
abort "fork source must be archived from GITHUB_SHA" unless archive && archive.fetch("run").include?("git -C \"$GITHUB_WORKSPACE\" archive --format=tar \"$GITHUB_SHA\"")
abort "source archive must be compressed deterministically" unless archive.fetch("run").include?("gzip -n -c")
abort "matrix outputs must be isolated per run, attempt, and gate" unless jobs.fetch("gate").fetch("steps").any? { |step| step.dig("env", "CARGO_TARGET_DIR") == "${{ runner.temp }}/cargo-target/${{ github.run_id }}-${{ github.run_attempt }}/${{ matrix.gate }}" }
required = jobs.fetch("required")
abort "required aggregate must always run after cancellation" unless required["if"] == "${{ always() }}"
abort "required aggregate must wait for prep and every matrix gate" unless required["needs"] == %w[prepare gate]
summary = required.fetch("steps").find { |step| step["name"] == "Require every CI gate to pass" }.fetch("run")
%w[success failure cancelled skipped].each do |result|
  env = { "PREPARE_RESULT" => result, "GATE_RESULT" => "success" }
  _out, _err, status = Open3.capture3(env, "bash", "-e", "-o", "pipefail", "-c", summary)
  abort "required aggregate accepted prepare result #{result}" if result != "success" && status.success?
  env = { "PREPARE_RESULT" => "success", "GATE_RESULT" => result }
  _out, _err, status = Open3.capture3(env, "bash", "-e", "-o", "pipefail", "-c", summary)
  abort "required aggregate accepted gate result #{result}" if result != "success" && status.success?
end

def git(dir, *args)
  output = IO.popen(["git", "-C", dir, *args], "r", &:read)
  abort "git #{args.join(' ')} failed" unless $?.success?
  output.strip
end

def run_step(step, workspace:, github_sha:, temp:)
  env = { "GITHUB_WORKSPACE" => workspace, "GITHUB_SHA" => github_sha, "RUNNER_TEMP" => temp }
  _stdout, _stderr, status = Open3.capture3(env, "/bin/bash", "-e", "-o", "pipefail", "-c", step.fetch("run"), chdir: workspace)
  status.success?
end

Dir.mktmpdir("crispy-runner-workflow-") do |root|
  repo = File.join(root, "repo")
  workspace_link = File.join(root, "workspace")
  temp = File.join(root, "runner-temp")
  extracted = File.join(root, "extracted")
  FileUtils.mkdir_p([repo, temp, extracted])
  git(repo, "init", "-q")
  git(repo, "config", "user.name", "Workflow Contract Test")
  git(repo, "config", "user.email", "workflow-contract@example.invalid")

  File.write(File.join(repo, "source.txt"), "base\n")
  git(repo, "add", "source.txt")
  git(repo, "commit", "-qm", "base")
  base_sha = git(repo, "rev-parse", "HEAD")

  File.write(File.join(repo, "source.txt"), "PR head\n")
  git(repo, "commit", "-qam", "PR head")
  pr_head_sha = git(repo, "rev-parse", "HEAD")
  FileUtils.ln_s(repo, workspace_link)

  File.write(File.join(repo, "merge-only.txt"), "merge result\n")
  git(repo, "add", "merge-only.txt")
  tree_sha = git(repo, "write-tree")
  merge_sha = git(repo, "commit-tree", tree_sha, "-p", base_sha, "-p", pr_head_sha, "-m", "PR merge result")

  File.write(File.join(repo, "untracked.txt"), "must not ship\n")
  FileUtils.mkdir_p(File.join(repo, "target"))
  File.write(File.join(repo, "target", "build.txt"), "must not ship\n")

  source_checks.each do |source_check|
    abort "matching same-repo PR workspace rejected" unless run_step(source_check, workspace: workspace_link, github_sha: pr_head_sha, temp: temp)
    abort "workspace at a different GITHUB_SHA accepted" if run_step(source_check, workspace: workspace_link, github_sha: merge_sha, temp: temp)
    abort "same-SHA unrelated workspace root accepted without the brokered symlink" if run_step(source_check, workspace: repo, github_sha: pr_head_sha, temp: temp)
  end

  abort "fork archive generation failed" unless run_step(archive, workspace: repo, github_sha: merge_sha, temp: temp)
  system("tar", "-xzf", File.join(temp, "source.tar.gz"), "-C", extracted) || abort("source archive extraction failed")
  abort "archive did not use the merge SHA" unless File.read(File.join(extracted, "merge-only.txt")) == "merge result\n"
  abort "archive omitted PR content" unless File.read(File.join(extracted, "source.txt")) == "PR head\n"
  abort "archive included untracked content" if File.exist?(File.join(extracted, "untracked.txt"))
  abort "archive included build output" if File.exist?(File.join(extracted, "target"))
  abort "archive included .git" if File.exist?(File.join(extracted, ".git"))
end
