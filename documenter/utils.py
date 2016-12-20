"""Utilities."""
from os import utime
from subprocess import Popen, PIPE
from termcolor import colored
import re


GH_REGEXS = [re.compile('github.com/(.+)/(.+)(?:\.git){1}'),
             re.compile('github.com/(.+)/(.+)'),
             re.compile('github.com:(.+)/(.+).git')]


def get_github_username_repo(url):
    """Extract Github username and repo from an url."""
    if 'github' in url:
        for regex in GH_REGEXS:
            match = regex.search(url)
            if match:
                return match.groups()
    return (None, None)


def touch(fname):
    """Touch a file (unix-style)."""
    with open(fname, 'a'):
        utime(fname, None)


def read_stdout(command):
    """Execute `command` and return its output and error message."""
    p = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    return p.communicate()


def print_with_color(msg, color):
    """Print strings in a color specified as a string.

    :parameters:
        :color: any of the values 'grey', 'blue', 'cyan',
            'green', 'magenta', 'red', 'white' or 'yellow'.
            :msg:   message to display.
    """
    print colored(msg, color)
