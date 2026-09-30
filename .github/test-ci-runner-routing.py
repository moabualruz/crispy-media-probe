from pathlib import Path
import unittest


WORKFLOWS = Path(__file__).with_name("workflows")
CI_TRUSTED_RUNNER_EXPRESSION = (
    "${{ (github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository && "
    "fromJSON(format('[\"self-hosted\", \"linux\", \"x64\", \"generic\", \"pr-{0}-{1}\"]', "
    "github.repository_id, github.event.pull_request.number))) || "
    "((github.event_name == 'push' || github.event_name == 'workflow_dispatch') && "
    "github.ref == 'refs/heads/main' && "
    "github.actor == github.repository_owner && "
    "fromJSON('[\"self-hosted\", \"linux\", \"x64\", \"generic\"]')) || "
    "'ubuntu-latest' }}"
)
CI_TRUSTED_PR_CHECKOUT_CONDITION = (
    "github.event_name != 'pull_request' || "
    "github.event.pull_request.head.repo.full_name != github.repository"
)
RELEASE_TRUSTED_RUNNER_EXPRESSION = (
    "${{ github.event_name == 'workflow_dispatch' && "
    "github.ref == 'refs/heads/main' && "
    "github.actor == github.repository_owner && "
    "fromJSON('[\"self-hosted\", \"linux\", \"x64\", \"generic\"]') || "
    "'ubuntu-latest' }}"
)


def runner(
    workflow,
    event,
    ref,
    head_repo="",
    author="",
    actor="moabualruz",
    repository_id=123,
    pr_number=7,
    run_id=55,
    run_attempt=1,
):
    if workflow == "release":
        trusted = (
            event == "workflow_dispatch"
            and ref == "refs/heads/main"
            and actor == "moabualruz"
        )
        return "self-hosted" if trusted else "ubuntu-latest"
    else:
        trusted_push = event == "push" and ref == "refs/heads/main"
        trusted_dispatch = event == "workflow_dispatch" and ref == "refs/heads/main"
        trusted_pr = (
            event == "pull_request"
            and head_repo == "moabualruz/crispy-media-probe"
        )
        trusted_push = trusted_push and actor == "moabualruz"
        trusted_dispatch = trusted_dispatch and actor == "moabualruz"
        if trusted_pr:
            return f"self-hosted:pr-{repository_id}-{pr_number}"
        return "self-hosted" if trusted_push or trusted_dispatch else "ubuntu-latest"


def checkout_enabled(event, head_repo="", author="", actor="moabualruz"):
    trusted_pr = (
        event == "pull_request"
        and head_repo == "moabualruz/crispy-media-probe"
    )
    return not trusted_pr


class RunnerRoutingTests(unittest.TestCase):
    def test_workflow_uses_the_tested_trust_expression(self):
        ci = (WORKFLOWS / "ci.yml").read_text()
        release = (WORKFLOWS / "release.yml").read_text()
        self.assertEqual(ci.count(f"runs-on: {CI_TRUSTED_RUNNER_EXPRESSION}"), 2)
        self.assertIn(f"if: {CI_TRUSTED_PR_CHECKOUT_CONDITION}", ci)
        self.assertIn("ref: ${{ github.sha }}", ci)
        self.assertIn("group: crispy-media-probe-pr-${{ github.event.pull_request.number || github.ref }}", ci)
        self.assertIn("cancel-in-progress: false", ci)
        self.assertIn("if: ${{ always() }}", ci)
        self.assertIn("  required:\n", ci)
        self.assertIn("needs: [prepare, gate]", ci)
        self.assertIn(f"runs-on: {RELEASE_TRUSTED_RUNNER_EXPRESSION}", release)

    def test_ci_prepares_source_once_then_runs_independent_gates(self):
        ci = (WORKFLOWS / "ci.yml").read_text()
        gate = ci.split("  gate:\n", maxsplit=1)[1]
        self.assertEqual(ci.count("uses: actions/checkout@v4"), 1)
        self.assertIn("  prepare:\n", ci)
        self.assertIn("    needs: prepare\n", gate)
        self.assertIn("        gate: [fmt, clippy, test, doc, package]", gate)
        self.assertNotIn("uses: actions/checkout@v4", gate)
        self.assertEqual(ci.count("uses: actions/cache@v4"), 1)
        self.assertIn("actions/cache/restore@v4", gate)
        self.assertIn(f"if: {CI_TRUSTED_PR_CHECKOUT_CONDITION}", gate)
        self.assertIn("actions/upload-artifact@v4", ci)
        self.assertIn("actions/download-artifact@v4", gate)
        self.assertIn("${{ runner.temp }}/cargo-target/${{ github.run_id }}-${{ github.run_attempt }}/${{ matrix.gate }}", gate)

    def test_artifact_name_survives_rerun_of_failed_jobs(self):
        ci = (WORKFLOWS / "ci.yml").read_text()
        for line in ci.splitlines():
            if line.strip().startswith("name: source-"):
                self.assertNotIn("run_attempt", line)
        self.assertEqual(ci.count("overwrite: true"), ci.count("actions/upload-artifact@"))

    def test_same_repository_pr_is_trusted_regardless_of_author_or_actor(self):
        self.assertEqual(
            runner("ci", "pull_request", "", "moabualruz/crispy-media-probe", "contributor", actor="contributor"),
            "self-hosted:pr-123-7",
        )

    def test_same_pr_runs_and_attempts_reuse_one_label(self):
        first = runner(
            "ci", "pull_request", "", "moabualruz/crispy-media-probe", "moabualruz", run_id=900
        )
        retry = runner(
            "ci",
            "pull_request",
            "",
            "moabualruz/crispy-media-probe",
            "moabualruz",
            run_id=900,
            run_attempt=2,
        )
        parallel = runner(
            "ci", "pull_request", "", "moabualruz/crispy-media-probe", "moabualruz", run_id=901
        )
        other_pr = runner(
            "ci", "pull_request", "", "moabualruz/crispy-media-probe", "moabualruz", pr_number=8
        )
        other_repo = runner(
            "ci",
            "pull_request",
            "",
            "moabualruz/crispy-media-probe",
            "moabualruz",
            repository_id=124,
        )
        self.assertEqual(first, "self-hosted:pr-123-7")
        self.assertEqual(retry, first)
        self.assertEqual(parallel, first)
        self.assertEqual(other_pr, "self-hosted:pr-123-8")
        self.assertEqual(other_repo, "self-hosted:pr-124-7")
        self.assertEqual(len({first, other_pr, other_repo}), 3)

    def test_every_same_repository_pr_skips_checkout(self):
        self.assertFalse(
            checkout_enabled("pull_request", "moabualruz/crispy-media-probe", "moabualruz")
        )
        self.assertFalse(
            checkout_enabled("pull_request", "moabualruz/crispy-media-probe", "contributor")
        )
        self.assertTrue(
            checkout_enabled("pull_request", "contributor/crispy-media-probe", "moabualruz")
        )
        self.assertFalse(
            checkout_enabled(
                "pull_request",
                "moabualruz/crispy-media-probe",
                "moabualruz",
                actor="contributor",
            )
        )
        self.assertTrue(checkout_enabled("push", actor="moabualruz"))

    def test_same_repository_pr_actor_does_not_change_runner_route(self):
        self.assertEqual(
            runner(
                "ci",
                "pull_request",
                "",
                "moabualruz/crispy-media-probe",
                "moabualruz",
                actor="contributor",
            ),
            "self-hosted:pr-123-7",
        )

    def test_same_repository_pr_author_does_not_change_runner_route(self):
        self.assertEqual(
            runner("ci", "pull_request", "", "moabualruz/crispy-media-probe", "contributor"),
            "self-hosted:pr-123-7",
        )

    def test_fork_pr_uses_hosted_runner_even_when_owner_authored(self):
        self.assertEqual(
            runner("ci", "pull_request", "", "contributor/crispy-media-probe", "moabualruz"),
            "ubuntu-latest",
        )

    def test_ci_manual_dispatch_from_owner_main_uses_personal_runner(self):
        self.assertEqual(runner("ci", "workflow_dispatch", "refs/heads/main"), "self-hosted")

    def test_ci_manual_dispatch_from_non_main_or_non_owner_uses_hosted_runner(self):
        self.assertEqual(
            runner("ci", "workflow_dispatch", "refs/heads/feature"), "ubuntu-latest"
        )
        self.assertEqual(
            runner("ci", "workflow_dispatch", "refs/heads/main", actor="contributor"),
            "ubuntu-latest",
        )

    def test_release_dispatch_from_main_by_owner_is_trusted(self):
        self.assertEqual(
            runner("release", "workflow_dispatch", "refs/heads/main", actor="moabualruz"),
            "self-hosted",
        )

    def test_release_dispatch_from_selected_non_main_ref_uses_hosted_runner(self):
        self.assertEqual(
            runner("release", "workflow_dispatch", "refs/heads/contributor-work", actor="moabualruz"),
            "ubuntu-latest",
        )

    def test_release_dispatch_by_non_owner_uses_hosted_runner(self):
        self.assertEqual(
            runner("release", "workflow_dispatch", "refs/heads/main", actor="contributor"),
            "ubuntu-latest",
        )

    def test_main_push_uses_trusted_runner(self):
        self.assertEqual(runner("ci", "push", "refs/heads/main"), "self-hosted")

    def test_non_owner_main_push_uses_hosted_runner(self):
        self.assertEqual(
            runner("ci", "push", "refs/heads/main", actor="contributor"),
            "ubuntu-latest",
        )

    def test_unpack_step_replaces_stale_workspace_with_exact_source(self):
        import re, subprocess, tarfile, tempfile, os
        text = Path(__file__).with_name("workflows").joinpath("ci.yml").read_text()
        gate = text.split("\n  gate:\n", 1)[1].split("\n  required:\n", 1)[0]
        match = re.search(
            r"- name: unpack checked out source for hosted jobs\n(?:        if: .*\n)?        run: \|\n((?:          .*\n)+)",
            gate,
        )
        self.assertTrue(match, "unpack step not found")
        script = "\n".join(line[10:] for line in match.group(1).splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            work, temp = Path(tmp, "ws"), Path(tmp, "tmp")
            (temp / "source").mkdir(parents=True)
            work.mkdir()
            (work / "stale.txt").write_text("left over from an earlier run")
            (work / ".hidden").write_text("stale")
            (work / "keep.txt").write_text("old")
            src = Path(tmp, "src")
            src.mkdir()
            (src / "keep.txt").write_text("new")
            with tarfile.open(temp / "source" / "source.tar.gz", "w:gz") as archive:
                archive.add(src / "keep.txt", arcname="keep.txt")
            subprocess.run(
                ["bash", "-e", "-c", script],
                check=True,
                env={**os.environ, "GITHUB_WORKSPACE": str(work), "RUNNER_TEMP": str(temp)},
            )
            self.assertEqual(sorted(p.name for p in work.iterdir()), ["keep.txt"])
            self.assertEqual((work / "keep.txt").read_text(), "new")


if __name__ == "__main__":
    unittest.main()
