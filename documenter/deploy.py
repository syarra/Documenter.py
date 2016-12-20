import tempfile
from os import chdir as cd
from os.path import exists, isfile
from os.path import join as joinpath
from os.path import abspath, splitext
from os.path import expanduser
from os import mkdir, chmod, environ
from shutil import move as mv
import subprocess
from subprocess import Popen, PIPE
from shutil import rmtree as rm
from base64 import b64decode
import stat
import sys

from documenter.utils import get_github_username_repo, touch

SSH_CONFIG = """
    Host github.com
        StrictHostKeyChecking no
        HostName github.com
        IdentityFile %s
"""

PULL_REQUEST_FLAGS = {'travis': "TRAVIS_PULL_REQUEST",
                      'jenkins': "JENKINS_PULL_REQUEST"}


class Documentation(object):

    def __init__(self, root, repo, **kwargs):
        self.root = root
        self.repo = repo
        self.target = kwargs.get('target', "build")
        self.branch = kwargs.get('branch', "gh-pages")
        self.latest = kwargs.get('latest', "master")
        self.make = kwargs.get('make', ["make", "html"])
        self.dirname = kwargs.get('dirname', "")
        self.host = kwargs.get('host', "github")
        self.original_ssh_config = None

    def restore_ssh_config(self):
        if self.original_ssh:
            with open(joinpath(self.home, ".ssh", "config"), "w") as sshconfig:
                sshconfig.write(SSH_CONFIG % key_file)

    def create_ssh_config(self, key_file):
        self.home = expanduser("~")
        self.ssh_config_file = joinpath(self.home, ".ssh", "config")
        # Use a custom SSH config file to avoid overwriting the default user
        # config.
        if exists(self.ssh_config_file):
            with open(self.ssh_config_file, "r") as sshconfig:
                self.original_ssh_config = sshconfig.read()

        with open(joinpath(self.home, ".ssh", "config"), "w") as sshconfig:
            sshconfig.write(SSH_CONFIG % key_file)

    def is_pull_request(self):
        try:
			return os.environ[PULL_REQUEST_FLAGS[self.host]]
		except KeyError:
			return False

    def deploy(self):
        """
        Build documentation in directory `root/target` and pushes it to `repo`.

        :Inputs:

            `root`: root directory where the `conf.py` file is.

            `repo`: remote repository where generated HTML content should be pushed to.

            `target`: directory relative to `root`, where generated HTML content should be
                      written to. This directory **must** be added to the repository's `.gitignore` file.
                      (default: `"site"`)

            `branch`: branch where the generated documentation is pushed.
                      (default: `"gh-pages"`)

            `latest`: branch that "tracks" the latest generated documentation.
                      (default: `"master"`)

            `make`: list of commands to be used to convert the markdown files to HTML.
                    (default: ['make', 'html'])
        """
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"])

        if self.is_pull_request():
            print_with_color("Documentation not ", 'magenta')
            break

        upstream = self.repo
        github_user, github_repo = get_github_username_repo(self.repo)

        enc_key_file = abspath(joinpath(self.root, ".documenter.enc"))
        has_ssh_key = isfile(enc_key_file)

        with open(enc_key_file, "r") as enc_keyfile:
            enc_key = enc_keyfile.read()

        key_file, _ = splitext(enc_key_file)
        with open(key_file, "w") as keyfile:
            keyfile.write(b64decode(enc_key))

        # Give READ/WRITE permissions
        chmod(key_file, stat.S_IREAD)
        chmod(key_file, stat.S_IWRITE)

        self.create_ssh_config(key_file)

        cd(root)

        tmp_dir = tempfile.mkdtemp()
        print tmp_dir

        docs = joinpath(self.root, "docs")
        cd(docs)
        if not exists(self.target):
            mkdir(self.target)
            subprocess.call(self.make)

        # Versioned docs directories.
        latest_dir = joinpath(self.dirname, "latest")
        stable_dir = joinpath(self.dirname, "stable")
        target_dir = joinpath(docs, self.target)

        # Setup git.
        cd(tmp_dir)
        subprocess.call(["git", "init"])
        subprocess.call(["git", "config", "user.name", "'autodocs'"])
        subprocess.call(["git", "config", "user.email", "'autodocs'"])

        # Fetch from remote and checkout the branch.
        if subprocess.call(["git", "remote", "add", "upstream", self.upstream]):
            raise RuntimeError("could not add new remote repo.")

        p = Popen(["git", "fetch", "upstream"],
                  stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, err = p.communicate()
        if p.returncode:
            raise RuntimeError(
                "could not fetch from remote: %s\n%s" % (output, err))

        p = Popen(["git", "checkout", "-b", branch, "upstream/" + branch],
                  stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, err = p.communicate()

        if "Cannot update paths and switch to branch" in err:
            try:
                subprocess.call(
                    ["git", "checkout", "--orphan", self.branch])
                subprocess.call(["git", "rm", "--cached", "-r", "."])
            except:
                raise RuntimeError("could not checkout remote branch.")
        else:
            raise RuntimeError(
                "could not checkout remote branch: %s\n%s" % (output, err))

        # Copy docs to `latest`, or `stable`, `<release>`, and `<version>`
        # directories.
        print latest_dir
        if exists(latest_dir):
            rm(latest_dir)
            mv(joinpath(target_dir, "html"), latest_dir)

        # Create a .nojekyll file so that Github pages behaves correctly with folders starting
        # with an underscore.
        touch('.nojekyll')

        with open('index.html', 'w') as f:
            f.write('<meta http-equiv="refresh" content="0; url=http://%s.github.io/%s/latest"/>' %
                    (github_user, github_repo))

        # Add, commit, and push the docs to the remote.
        subprocess.call(["git", "add", "-A", "."])

        subprocess.call(["git", "commit", "-m", "build based on %s" % sha])

        if subprocess.call(["git", "push", "-q", "upstream", "HEAD:%s" % self.branch]):
            raise RuntimeError("could not push to remote repo.")

        # Clean up temporary directories
        rm(target_dir)
        rm(tmp_dir)
        # Restore user defined ssh configuration
        self.restore_ssh_config()
