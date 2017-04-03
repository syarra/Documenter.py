import tempfile
from os import chdir as cd
from os import environ, getcwd
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
    Host %s
        StrictHostKeyChecking no
        HostName %s
        IdentityFile %s
"""

HOST_URL = {'github': "github.com"}

PULL_REQUEST_FLAGS = {'travis': "TRAVIS_PULL_REQUEST",
                      'jenkins': "JENKINS_PULL_REQUEST"}
TAG_FLAGS = {'travis': "TRAVIS_TAG",
             'jenkins': "JENKINS_TAG"}


class Documentation(object):

    def __init__(self, repo, **kwargs):
        self.root = getcwd()
        self.repo = repo
        self.target = kwargs.get('target', "build")
        self.branch = kwargs.get('branch', "gh-pages")
        self.latest = kwargs.get('latest', "master")
        self.make = kwargs.get('make', ["make", "html"])
        self.dirname = kwargs.get('dirname', "")
        self.host = kwargs.get('host', "github")
        self.original_ssh_config = None
        self.local_upstream = kwargs.get('local_upstream', None)
        self.key_file = None

    def restore_ssh_config(self):
        if self.original_ssh_config:
            with open(joinpath(self.home, ".ssh", "config"), "w") as sshconfig:
                sshconfig.write(self.original_ssh_config)

    def create_ssh_config(self):
        self.home = expanduser("~")
        self.ssh_config_file = joinpath(self.home, ".ssh", "config")
        # Use a custom SSH config file to avoid overwriting the default user
        # config.
        if exists(self.ssh_config_file):
            with open(self.ssh_config_file, "r") as sshconfig:
                self.original_ssh_config = sshconfig.read()

        with open(self.ssh_config_file, "w") as sshconfig:
            sshconfig.write(SSH_CONFIG % (HOST_URL[self.host],
                                          HOST_URL[self.host],
                                          self.key_file))

    def is_pull_request(self):
        try:
            return environ[PULL_REQUEST_FLAGS[self.host]]
        except KeyError:
            return False

    def is_tagged(self):
        try:
            return environ[TAG_FLAGS[self.host]]
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

            `local_upstream`: remote repository to fetch from.
                        (default: `None`)

            `make`: list of commands to be used to convert the markdown files to HTML.
                    (default: ['make', 'html'])
        """
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).strip()
        current_branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'])

        host_user, host_repo = get_github_username_repo(self.repo)
        print host_user, host_repo

        self.upstream = "git@%s:%s/%s.git" % (HOST_URL[self.host],
                                                  host_user,
                                                  host_repo)

        if self.local_upstream is not None:
	    # Pull the documentation branch to avoid conflicts
            print "git", "checkout", self.branch
            p = Popen(["git", "checkout", self.branch],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)
            p.communicate()
            # print subprocess.check_output(["git", "checkout", self.branch])
            print subprocess.check_output(["git", "branch"])
            print "git", "pull", "origin", self.branch
            p = Popen(["git", "pull", "origin", self.branch],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, err = p.communicate()
            if p.returncode:
                raise RuntimeError(
                    "could not update the local upstream: %s\n%s" % (output, err))
            print "git", "checkout", "-f", sha
            p = Popen(["git", "checkout", "-f", sha],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)
            output, err = p.communicate()
            print subprocess.check_output(["git", "branch"])


        enc_key_file = abspath(joinpath(self.root, "docs", ".documenter.enc"))
        has_ssh_key = isfile(enc_key_file)

        with open(enc_key_file, "r") as enc_keyfile:
            enc_key = enc_keyfile.read()

        self.key_file, _ = splitext(enc_key_file)
        with open(self.key_file, "w") as keyfile:
            keyfile.write(b64decode(enc_key))

        # Give READ/WRITE permissions
        chmod(self.key_file, stat.S_IREAD | stat.S_IWRITE)

        self.create_ssh_config()

        tmp_dir = tempfile.mkdtemp()
        print tmp_dir

        docs = joinpath(self.root, "docs")
        cd(docs)
        if not exists(self.target):
            mkdir(self.target)
        subprocess.call(self.make)

        if self.is_pull_request():
            print_with_color("Skipping documentation deployment", 'magenta')
            return

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
        if self.local_upstream is not None:
            if subprocess.call(["git", "remote", "add", "local_upstream", self.local_upstream]):
                raise RuntimeError("could not add new remote repo.")
        if subprocess.call(["git", "remote", "add", "upstream", self.upstream]):
            raise RuntimeError("could not add new remote repo.")

        if self.local_upstream is not None:
            p = Popen(["git", "fetch", "local_upstream"],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)
        else:
            p = Popen(["git", "fetch", "upstream"],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)

        output, err = p.communicate()
        if p.returncode:
            raise RuntimeError(
                "could not fetch from upstream: %s\n%s" % (output, err))

        if self.local_upstream is not None:
            p = Popen(["git", "checkout", "-b", self.branch, "local_upstream/" + self.branch],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)
        else:
            p = Popen(["git", "checkout", "-b", self.branch, "upstream/" + self.branch],
                      stdin=PIPE, stdout=PIPE, stderr=PIPE)
        output, err = p.communicate()

        if "Cannot update paths and switch to branch" in err:
            try:
                subprocess.call(
                    ["git", "checkout", "--orphan", self.branch])
                subprocess.call(["git", "rm", "--cached", "-r", "."])
            except:
                raise RuntimeError("could not checkout remote branch.")
        elif p.returncode:
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
                    (host_user, host_repo))

        # Add, commit, and push the docs to the remote.
        subprocess.call(["git", "add", "-A", "."])

        subprocess.call(["git", "commit", "-m", "build based on %s" % sha])

        if subprocess.call(["git", "push", "-q", "-f", "upstream", "HEAD:%s" % self.branch]):
            raise RuntimeError("could not push to remote repo.")

        # Clean up temporary directories
        rm(target_dir)
        rm(tmp_dir)

        # Restore user defined ssh configuration
        self.restore_ssh_config()
