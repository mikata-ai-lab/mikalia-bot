"""
test_github_tools.py — Tests para git commit, push, branch y GitHub PR tools.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mikalia.tools.github_tools import (
    GitCommitTool,
    GitPushTool,
    GitBranchTool,
    GitHubPRTool,
    _is_blocked_file,
    _run_git,
    BLOCKED_FILES,
)


# ================================================================
# _is_blocked_file
# ================================================================

class TestBlockedFiles:
    def test_env_blocked(self):
        assert _is_blocked_file(".env") is True

    def test_env_local_blocked(self):
        assert _is_blocked_file(".env.local") is True

    def test_credentials_blocked(self):
        assert _is_blocked_file("credentials.json") is True

    def test_pem_blocked(self):
        assert _is_blocked_file("server.pem") is True

    def test_key_blocked(self):
        assert _is_blocked_file("private.key") is True

    def test_id_rsa_blocked(self):
        assert _is_blocked_file("id_rsa") is True

    def test_normal_file_allowed(self):
        assert _is_blocked_file("README.md") is False

    def test_python_file_allowed(self):
        assert _is_blocked_file("src/main.py") is False

    def test_case_insensitive(self):
        assert _is_blocked_file(".ENV") is True

    def test_path_with_dir(self):
        assert _is_blocked_file("config/.env") is True


# ================================================================
# GitCommitTool
# ================================================================

class TestGitCommitTool:
    def test_claude_definition(self):
        tool = GitCommitTool()
        d = tool.to_claude_definition()
        assert d["name"] == "git_commit"
        assert "files" in d["input_schema"]["properties"]
        assert "message" in d["input_schema"]["properties"]

    def test_blocked_file_rejected(self):
        tool = GitCommitTool()
        result = tool.execute(
            files=".env, main.py",
            message="bad commit",
            repo_path=".",
        )
        assert not result.success
        assert "bloqueado" in result.error.lower()

    def test_credentials_rejected(self):
        tool = GitCommitTool()
        result = tool.execute(
            files="credentials.json",
            message="oops",
            repo_path=".",
        )
        assert not result.success

    def test_not_a_repo(self, tmp_path):
        tool = GitCommitTool()
        result = tool.execute(
            files="README.md",
            message="test",
            repo_path=str(tmp_path),
        )
        assert not result.success
        assert "No es un repo git" in result.error

    @patch("mikalia.tools.github_tools._run_git")
    def test_successful_commit(self, mock_git):
        mock_git.side_effect = [
            MagicMock(returncode=0, stderr=""),           # git add
            MagicMock(returncode=0, stderr=""),           # git commit
            MagicMock(returncode=0, stdout="abc1234\n"),  # git rev-parse
        ]
        tool = GitCommitTool()
        result = tool.execute(files="main.py", message="update", repo_path=".")
        assert result.success
        assert "abc1234" in result.output

    @patch("mikalia.tools.github_tools._run_git")
    def test_nothing_to_commit(self, mock_git):
        mock_git.side_effect = [
            MagicMock(returncode=0, stderr=""),                     # git add
            MagicMock(returncode=1, stderr="nothing to commit", stdout=""),  # git commit
        ]
        tool = GitCommitTool()
        result = tool.execute(files="main.py", message="test", repo_path=".")
        assert result.success
        assert "limpio" in result.output.lower()

    @patch("mikalia.tools.github_tools._run_git")
    def test_commit_all(self, mock_git):
        mock_git.side_effect = [
            MagicMock(returncode=0, stderr=""),
            MagicMock(returncode=0, stderr=""),
            MagicMock(returncode=0, stdout="def5678\n"),
        ]
        tool = GitCommitTool()
        result = tool.execute(files="all", message="commit all", repo_path=".")
        assert result.success
        # Verify -A was passed
        mock_git.assert_any_call(["add", "-A"], cwd=".")

    @patch("mikalia.tools.github_tools._run_git")
    def test_git_add_failure(self, mock_git):
        mock_git.return_value = MagicMock(
            returncode=1, stderr="fatal: pathspec 'x' did not match"
        )
        tool = GitCommitTool()
        result = tool.execute(files="nonexistent.py", message="test", repo_path=".")
        assert not result.success

    @patch("mikalia.tools.github_tools._run_git")
    def test_timeout(self, mock_git):
        mock_git.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        tool = GitCommitTool()
        result = tool.execute(files="main.py", message="test", repo_path=".")
        assert not result.success
        assert "timeout" in result.error.lower()


# ================================================================
# GitPushTool
# ================================================================

class TestGitPushTool:
    def test_claude_definition(self):
        tool = GitPushTool()
        d = tool.to_claude_definition()
        assert d["name"] == "git_push"

    @patch("mikalia.tools.github_tools._run_git")
    def test_successful_push(self, mock_git):
        mock_git.return_value = MagicMock(
            returncode=0, stderr="To github.com:user/repo\n  main -> main"
        )
        tool = GitPushTool()
        result = tool.execute(repo_path=".")
        assert result.success
        assert "exitoso" in result.output.lower()

    @patch("mikalia.tools.github_tools._run_git")
    def test_push_with_branch(self, mock_git):
        mock_git.return_value = MagicMock(returncode=0, stderr="ok")
        tool = GitPushTool()
        result = tool.execute(repo_path=".", branch="feat/new")
        assert result.success
        mock_git.assert_called_once_with(
            ["push", "-u", "origin", "feat/new"], cwd=".", timeout=60
        )

    @patch("mikalia.tools.github_tools._run_git")
    def test_already_up_to_date(self, mock_git):
        mock_git.return_value = MagicMock(
            returncode=1, stderr="Everything up-to-date"
        )
        tool = GitPushTool()
        result = tool.execute(repo_path=".")
        assert result.success
        assert "actualizado" in result.output.lower()

    @patch("mikalia.tools.github_tools._run_git")
    def test_push_failure(self, mock_git):
        mock_git.return_value = MagicMock(
            returncode=1, stderr="rejected: non-fast-forward"
        )
        tool = GitPushTool()
        result = tool.execute(repo_path=".")
        assert not result.success

    @patch("mikalia.tools.github_tools._run_git")
    def test_push_timeout(self, mock_git):
        mock_git.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=60)
        tool = GitPushTool()
        result = tool.execute(repo_path=".")
        assert not result.success
        assert "timeout" in result.error.lower()


# ================================================================
# GitBranchTool
# ================================================================

class TestGitBranchTool:
    def test_claude_definition(self):
        tool = GitBranchTool()
        d = tool.to_claude_definition()
        assert d["name"] == "git_branch"
        assert "branch_name" in d["input_schema"]["properties"]

    @patch("mikalia.tools.github_tools._run_git")
    def test_create_branch(self, mock_git):
        mock_git.return_value = MagicMock(returncode=0, stderr="")
        tool = GitBranchTool()
        result = tool.execute(branch_name="mikalia/feat/new-tool", action="create")
        assert result.success
        mock_git.assert_called_once_with(
            ["checkout", "-b", "mikalia/feat/new-tool"], cwd="."
        )

    @patch("mikalia.tools.github_tools._run_git")
    def test_switch_branch(self, mock_git):
        mock_git.return_value = MagicMock(returncode=0, stderr="")
        tool = GitBranchTool()
        result = tool.execute(branch_name="main", action="switch")
        assert result.success
        mock_git.assert_called_once_with(
            ["checkout", "main"], cwd="."
        )

    @patch("mikalia.tools.github_tools._run_git")
    def test_branch_failure(self, mock_git):
        mock_git.return_value = MagicMock(
            returncode=1, stderr="fatal: branch already exists"
        )
        tool = GitBranchTool()
        result = tool.execute(branch_name="existing-branch")
        assert not result.success


# ================================================================
# GitHubPRTool
# ================================================================

class TestGitHubPRTool:
    def test_claude_definition(self):
        tool = GitHubPRTool()
        d = tool.to_claude_definition()
        assert d["name"] == "github_pr"
        assert "title" in d["input_schema"]["properties"]
        assert "body" in d["input_schema"]["properties"]

    @patch("mikalia.tools.github_tools.subprocess.run")
    @patch.object(GitHubPRTool, "_find_gh", return_value="gh")
    def test_successful_pr(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/user/repo/pull/42\n",
        )
        tool = GitHubPRTool()
        result = tool.execute(
            title="Add validation",
            body="## Summary\n- Added input validation",
        )
        assert result.success
        assert "pull/42" in result.output

    @patch.object(GitHubPRTool, "_find_gh", return_value=None)
    def test_gh_not_found(self, mock_find):
        tool = GitHubPRTool()
        result = tool.execute(title="Test", body="test")
        assert not result.success
        assert "gh CLI" in result.error

    @patch("mikalia.tools.github_tools.subprocess.run")
    @patch.object(GitHubPRTool, "_find_gh", return_value="gh")
    def test_pr_with_labels(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/user/repo/pull/1\n",
        )
        tool = GitHubPRTool()
        result = tool.execute(
            title="Fix bug",
            body="Fixed it",
            labels="bug,mikalia-authored",
        )
        assert result.success
        # Verify labels were passed
        call_args = mock_run.call_args[0][0]
        assert "--label" in call_args
        assert "bug" in call_args
        assert "mikalia-authored" in call_args

    @patch("mikalia.tools.github_tools.subprocess.run")
    @patch.object(GitHubPRTool, "_find_gh", return_value="gh")
    def test_pr_failure(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="pull request already exists",
            stdout="",
        )
        tool = GitHubPRTool()
        result = tool.execute(title="Dup", body="dup")
        assert not result.success

    @patch("mikalia.tools.github_tools.subprocess.run")
    @patch.object(GitHubPRTool, "_find_gh", return_value="gh")
    def test_pr_timeout(self, mock_find, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=30)
        tool = GitHubPRTool()
        result = tool.execute(title="Slow", body="slow")
        assert not result.success
        assert "timeout" in result.error.lower()

    @patch("mikalia.tools.github_tools.subprocess.run")
    @patch.object(GitHubPRTool, "_find_gh", return_value="gh")
    def test_pr_custom_base(self, mock_find, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/user/repo/pull/5\n",
        )
        tool = GitHubPRTool()
        result = tool.execute(
            title="Into develop",
            body="merge to develop",
            base="develop",
        )
        assert result.success
        call_args = mock_run.call_args[0][0]
        assert "--base" in call_args
        idx = call_args.index("--base")
        assert call_args[idx + 1] == "develop"
