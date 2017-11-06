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
import logging

from documenter.utils import get_github_username_repo, touch, print_with_color

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

def log_and_execute(cmd):
    """Logs and executes the provided command.

    Raises an error if the provided command fails to be executed.

    Args:
       cmd: List of instructions.
    """
    logging.debug(' '.join(map(str, cmd)))
    p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    output, err = p.communicate()
    if p.returncode and not 'nothing to commit, working directory clean' in output:
        raise RuntimeError("Could not run '%s'\nOutput: %s\nError: %s" % (' '.join(map(str, cmd)), output, err))
    return output


class Documentation(object):

    def __init__(self, repo, **kwargs):
        self.root = getcwd()
        self.repo = repo
        self.target = kwargs.get('target', "build")
        self.doc_branch = kwargs.get('doc_branch', "gh-pages")
        self.stable = kwargs.get('stable', "master")
        self.latest = kwargs.get('latest', "develop")
        self.stable_dir = kwargs.get('stable_dir', "stable")
        self.latest_dir = kwargs.get('latest_dir', "latest")
        self.make = kwargs.get('make', ["make", "html"])
        self.dirname = kwargs.get('dirname', "")
        self.host = kwargs.get('host', "github")
        self.ci = kwargs.get('ci', 'travis')
        self.original_ssh_config = None
        self.local_upstream = kwargs.get('local_upstream', None)
        self.key_file = None

        logging.basicConfig(format='%(asctime)s    %(message)s',
                        datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.DEBUG)

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
            logging.debug("Is a PR: %s" % environ[PULL_REQUEST_FLAGS[self.ci]])
            return eval(environ[PULL_REQUEST_FLAGS[self.ci]])
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

            `doc_branch`: branch where the generated documentation is pushed.
                      (default: `"gh-pages"`)

            `latest`: branch that "tracks" the latest generated documentation.
                      (default: `"develop"`)

            `local_upstream`: remote repository to fetch from.
                        (default: `None`)

            `make`: list of commands to be used to convert the markdown files to HTML.
                    (default: ['make', 'html'])
        """
        sha = log_and_execute(["git", "rev-parse", "HEAD"]).strip()
        current_branch = environ['GIT_BRANCH']
        logging.debug('current branch: %s' % current_branch)

        host_user, host_repo = get_github_username_repo(self.repo)
        logging.debug('host username: %s, host repo: %s', host_user, host_repo)

        self.upstream = "git@%s:%s/%s.git" % (HOST_URL[self.host],
                                                  host_user,
                                                  host_repo)

        logging.debug('upstream: %s' % self.upstream)
        if self.is_pull_request():
            print_with_color("Skipping documentation deployment", 'magenta')
            return

        if self.local_upstream is not None:
	    # Pull the documentation branch to avoid conflicts
            log_and_execute(["git", "checkout", self.doc_branch])
            log_and_execute(["git", "branch"])
            log_and_execute(["git", "pull", "origin", self.doc_branch])
            log_and_execute(["git", "checkout", "-f", sha])
            log_and_execute(["git", "branch"])


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
        logging.debug("temporary directory is: %s" %tmp_dir)

        docs = joinpath(self.root, "docs")
        cd(docs)
        if not exists(self.target):
            mkdir(self.target)
        log_and_execute(self.make)

        # Versioned docs directories.
        latest_dir = joinpath(self.dirname, self.latest_dir)
        stable_dir = joinpath(self.dirname, self.stable_dir)
        target_dir = joinpath(docs, self.target)

        # Setup git.
        cd(tmp_dir)
        log_and_execute(["git", "init"])
        log_and_execute(["git", "config", "user.name", "'autodocs'"])
        log_and_execute(["git", "config", "user.email", "'autodocs'"])

        # Fetch from remote and checkout the branch.
        if self.local_upstream is not None:
            log_and_execute(["git", "remote", "add", "local_upstream", self.local_upstream])

        log_and_execute(["git", "remote", "add", "upstream", self.upstream])
        log_and_execute(["git", "fetch", "upstream", self.doc_branch])
        try:
            log_and_execute(["git", "checkout", "-b", self.doc_branch, "upstream/" + self.doc_branch])
        except RuntimeError:
            try:
                log_and_execute(["git", "checkout",
                                 "--orphan", self.doc_branch])
                log_and_execute(["git", "rm", "--cached", "-r", "."])
            except:
                raise RuntimeError("could not checkout remote branch.")

        # Copy docs to `latest`, or `stable`, `<release>`, and `<version>`
        # directories.
        if current_branch == 'origin/' + self.latest:
            if exists(latest_dir):
                rm(latest_dir)
            logging.debug("Copying HTML folder to %s", latest_dir)
            mv(joinpath(target_dir, "html"), latest_dir)
        elif current_branch == 'origin/' + self.stable:
            if exists(stable_dir):
                rm(stable_dir)
            logging.debug("Copying HTML folder to %s", stable_dir)
            mv(joinpath(target_dir, "html"), stable_dir)

        # Create a .nojekyll file so that Github pages behaves correctly with folders starting
        # with an underscore.
        touch('.nojekyll')

        with open('index.html', 'w') as f:
            f.write('<meta http-equiv="refresh" content="0; url=http://%s.github.io/%s/stable"/>' %
                    (host_user, host_repo))

        # Add, commit, and push the docs to the remote.
        log_and_execute(["git", "add", "-A", "."])
        log_and_execute(["git", "commit", "-m", "'build based on %s'" % sha])
        log_and_execute(["git", "push", "-q", "upstream", "HEAD:%s" % self.doc_branch])

        # Clean up temporary directories
        rm(target_dir)
        rm(tmp_dir)

        # Restore user defined ssh configuration
        self.restore_ssh_config()
