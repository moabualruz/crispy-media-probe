from pathlib import Path
import unittest


WORKFLOWS = Path(__file__).with_name("workflows")
CI_TRUSTED_RUNNER_EXPRESSION = (
    "${{ (github.event_name == 'push' && github.ref == 'refs/heads/main' && "
    "github.actor == github.repository_owner || "
    "github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository && "
    "github.event.pull_request.user.login == github.repository_owner && "
    "github.actor == github.repository_owner) && "
    "fromJSON('[\"self-hosted\", \"linux\", \"x64\", \"generic\"]') || "
    "'ubuntu-latest' }}"
)
RELEASE_TRUSTED_RUNNER_EXPRESSION = (
    "${{ github.event_name == 'workflow_dispatch' && "
    "github.ref == 'refs/heads/main' && "
    "github.actor == github.repository_owner && "
    "fromJSON('[\"self-hosted\", \"linux\", \"x64\", \"generic\"]') || "
    "'ubuntu-latest' }}"
)


def runner(workflow, event, ref, head_repo="", author="", actor="moabualruz"):
    if workflow == "release":
        trusted = (
            event == "workflow_dispatch"
            and ref == "refs/heads/main"
            and actor == "moabualruz"
        )
    else:
        trusted_push = event == "push" and ref == "refs/heads/main"
        trusted_pr = (
            event == "pull_request"
            and head_repo == "moabualruz/crispy-media-probe"
            and author == "moabualruz"
            and actor == "moabualruz"
        )
        trusted_push = trusted_push and actor == "moabualruz"
        trusted = trusted_push or trusted_pr
    return "self-hosted" if trusted else "ubuntu-latest"


class RunnerRoutingTests(unittest.TestCase):
    def test_workflow_uses_the_tested_trust_expression(self):
        ci = (WORKFLOWS / "ci.yml").read_text()
        release = (WORKFLOWS / "release.yml").read_text()
        self.assertIn(f"runs-on: {CI_TRUSTED_RUNNER_EXPRESSION}", ci)
        self.assertIn(f"runs-on: {RELEASE_TRUSTED_RUNNER_EXPRESSION}", release)

    def test_owner_authored_same_repository_pr_is_trusted(self):
        self.assertEqual(
            runner("ci", "pull_request", "", "moabualruz/crispy-media-probe", "moabualruz"),
            "self-hosted",
        )

    def test_non_owner_push_to_owner_authored_pr_uses_hosted_runner(self):
        self.assertEqual(
            runner(
                "ci",
                "pull_request",
                "",
                "moabualruz/crispy-media-probe",
                "moabualruz",
                actor="contributor",
            ),
            "ubuntu-latest",
        )

    def test_same_repository_non_owner_pr_uses_hosted_runner(self):
        self.assertEqual(
            runner("ci", "pull_request", "", "moabualruz/crispy-media-probe", "contributor"),
            "ubuntu-latest",
        )

    def test_fork_pr_uses_hosted_runner_even_when_owner_authored(self):
        self.assertEqual(
            runner("ci", "pull_request", "", "contributor/crispy-media-probe", "moabualruz"),
            "ubuntu-latest",
        )

    def test_ci_manual_dispatch_uses_hosted_runner(self):
        self.assertEqual(runner("ci", "workflow_dispatch", "refs/heads/main"), "ubuntu-latest")

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


if __name__ == "__main__":
    unittest.main()
