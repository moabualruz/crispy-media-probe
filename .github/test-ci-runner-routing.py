from pathlib import Path
import unittest


WORKFLOW = Path(__file__).with_name("workflows") / "ci.yml"
TRUSTED_RUNNER_EXPRESSION = (
    "${{ (github.event_name == 'push' && github.ref == 'refs/heads/main' || "
    "github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name == github.repository && "
    "github.event.pull_request.user.login == github.repository_owner) && "
    "fromJSON('[\"self-hosted\", \"linux\", \"x64\", \"generic\"]') || "
    "'ubuntu-latest' }}"
)


def runner(event, ref, head_repo, author, repository="moabualruz/crispy-media-probe"):
    trusted_push = event == "push" and ref == "refs/heads/main"
    trusted_pr = (
        event == "pull_request"
        and head_repo == repository
        and author == repository.split("/", 1)[0]
    )
    return "self-hosted" if trusted_push or trusted_pr else "ubuntu-latest"


class RunnerRoutingTests(unittest.TestCase):
    def test_workflow_uses_the_tested_trust_expression(self):
        workflow = WORKFLOW.read_text()
        self.assertIn(f"runs-on: {TRUSTED_RUNNER_EXPRESSION}", workflow)

    def test_owner_authored_same_repository_pr_is_trusted(self):
        self.assertEqual(
            runner("pull_request", "", "moabualruz/crispy-media-probe", "moabualruz"),
            "self-hosted",
        )

    def test_same_repository_non_owner_pr_uses_hosted_runner(self):
        self.assertEqual(
            runner("pull_request", "", "moabualruz/crispy-media-probe", "contributor"),
            "ubuntu-latest",
        )

    def test_fork_pr_uses_hosted_runner_even_when_owner_authored(self):
        self.assertEqual(
            runner("pull_request", "", "contributor/crispy-media-probe", "moabualruz"),
            "ubuntu-latest",
        )


if __name__ == "__main__":
    unittest.main()
