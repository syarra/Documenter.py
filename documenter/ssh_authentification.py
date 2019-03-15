from os import chmod
from os.path import isfile
import subprocess
from documenter.utils import get_github_username_repo
from Crypto.PublicKey import RSA
from base64 import b64encode

from documenter.utils import read_stdout, print_with_color

HOST_URL = {'github': "https://github.com/%s/%s/settings/keys"}
CI_URL = {'travis': "https://travis-ci.org/%s/%s/settings"}


class Authentification(object):

    def __init__(self, package, remote="origin", host="github", ci="travis", ci_url=None):
        self.package = package
        self.remote = remote
        self.host = host
        self.host_url = HOST_URL[host]
        self.ci = ci
        if ci_url:
            self.ci_url = ci_url
        else:
            self.ci_url = CI_URL[ci]

        # Is this a git repo?
        output, err = read_stdout(['git', 'status'])
        if err:
            raise TypeError("Current directory is not a git repository.")

        # Find the GitHub repo org and name.
        url, err = read_stdout(
            ['git', 'config', '--get', 'remote.%s.url' % self.remote])
        if err:
            raise RuntimeError(
                "no remote repo named '%s' found." % self.remote)
        user, repo = get_github_username_repo(url)
        self.user = user
        self.repo = repo
        try:
            self.host_url = self.host_url % (user, repo)
            self.ci_url = self.ci_url % (user, repo)
        except:
            pass

    def genkeys(self, length=4096):

        key = RSA.generate(length)
        private_key = key.exportKey('PEM')
        public_key = key.publickey().exportKey('OpenSSH')
        return private_key, public_key

    def generate_ssh_keys(self, filename=".documenter"):
        # Check for old 'filename.enc' and terminate.
        if isfile(filename + ".enc"):
            raise RuntimeError(
                "%s already has an ssh key. Remove it and try again." % self.package)

        # Generate the ssh key pair.
        private_key, public_key = self.genkeys()

        # Prompt user to add public key to host server.
        print_with_color("Add the public key below to %s with read/write access:" %
                         self.host_url, "green")
        print(public_key)

        # Base64 encode the private key and store it to a file.
        b64key = b64encode(private_key)
        with open(filename + ".enc", "w") as key_file:
            key_file.write(b64key)
