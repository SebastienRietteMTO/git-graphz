#!/usr/bin/python3

"""
A python module and script to make a graph from a commit tree
"""

__author__ = 'Stephan Bechter <stephan@apogeum.at>'
__version__ = '1.1.0'

import subprocess
import re
import hashlib
import logging
import os
import tempfile
import xml.dom.minidom
import json
import argparse


class Gitgraphz():
    """
    Main class of gitgraphz
    """

    # colors
    COLOR_NODE = "cornsilk"
    COLOR_NODE_MERGE = "cornsilk2"
    COLOR_NODE_FIRST = "cornflowerblue"
    COLOR_NODE_CHERRY_PICK = "burlywood1"
    COLOR_NODE_REVERT = "azure4"
    COLOR_HEAD = "darkgreen"
    COLOR_TAG = "yellow2"
    COLOR_BRANCH = "orange"
    COLOR_STASH = "red"

    def __init__(self, repository=None, url=None):
        """
        Tool to create a graph from a git history showing tags, branches, stash nodes, cherry-picks.
        :param repository: directory containing the repository to use
                           None to use the current working directory
                           otherwise, must be a string used as a git url
        :param url: repository url to use for html output
        """
        if repository is None or os.path.isdir(repository):
            self.url = url
            self.repository = repository
        else:
            self.url = repository
            # will be deleted when self._tmpdir will be garbage collected
            self._tmpdir = tempfile.TemporaryDirectory()
            self.repository = self._tmpdir.name
            command = ['git', 'clone', repository, '.']
            logging.info('Git command: %s', ' '.join(command))
            status = subprocess.run(command, cwd=self.repository, check=False).returncode
            if status != 0:
                raise RuntimeError(
                    f"Error during repository cloning using the url: {str(repository)}")
        if self.url is not None and not self.url.startswith('https://'):
            self.url = None
        command = ['git', 'rev-parse']
        logging.info('Git command: %s', ' '.join(command))
        status = subprocess.run(command, cwd=self.repository, check=False).returncode
        if status != 0:
            if repository is None:
                message = "It seems that current working directory is not inside a git repository!"
            else:
                message = f"It seems that this directory ({repository}) is not a git repository!"
            raise RuntimeError(message)

        self.pattern = re.compile(r'^\[(\d+)\|\|(.*)\|\|(.*)\|\|\s?(.*)\]' +
                                  r'\s([0-9a-f]*)\s?([0-9a-f]*)\s?([0-9a-f]*)$')
        self.reverse_message_pattern = re.compile(r'Revert "(.*)"')

    def get_log(self, rev_range=None, options=None):
        """
        :param rev_range: git commit range to deal with
        :param options: - dictionary containing other options to use for log command
                        - or None, in this case '--all' option is used
                        use an empty dictionary ([]) to suppress all options
        """
        if rev_range is not None:
            logging.info("Range: %s", rev_range)
            rev_range = [rev_range]
        else:
            rev_range = []
        if options is None:
            options = ['--all']
        git_log_command = ['git', 'log', '--pretty=format:[%ct||%cn||%s||%d] %h %p']
        git_log_command += options + rev_range
        logging.info('Git log command: %s', ' '.join(git_log_command))
        out = subprocess.run(git_log_command, cwd=self.repository, capture_output=True,
                             universal_newlines=True, check=True).stdout.split('\n')
        return out

    def get_commit_diff(self, commit):
        """
        Get the differences introduced by a commit
        :param commit: commit's hash
        """
        command = ['git', 'diff', commit + '^', commit]
        logging.debug("Hash Command: %s", ' '.join(command))
        diff = subprocess.run(command, cwd=self.repository, capture_output=True, check=True).stdout
        # get only the changed lines (starting with + or -), no line numbers, hashes, ...
        diff = b'\n'.join([line for line in diff.splitlines()
                           if (line.startswith(b'+') or line.startswith(b'-'))])
        return diff

    def get_commit_diff_hash(self, commit):
        """
        Get the hash value of the differences introduced by a commit
        :param commit: commit's hash
        """
        diff = self.get_commit_diff(commit)
        sha = hashlib.sha1(diff)
        return sha.hexdigest()

    def get_dot(self, show_messages=False, rev_range=None, log_options=None):
        """
        :param show_messages (optional): Show commit messages in node
        :param rev_range (optional): git commit range to deal with
        :param log_options: - dictionary containing other options to use for log command
                           - or None, in this case '-all' option is used
                           use an empty dictionary ([]) to suppress all options
        """
        lines = self.get_log(rev_range, log_options)

        dates = {}
        messages = {}
        predefined_node_color = {}

        digraph = "digraph G {"
        # first extract messages
        for line in lines:
            match = re.match(self.pattern, line)
            if match:
                date = match.group(1)
                message = match.group(3)
                commit_hash = match.group(5)
                if message in messages:
                    existing = messages[message]
                    if dates[existing] > date:
                        messages[message] = commit_hash
                else:
                    messages[message] = commit_hash
                dates[commit_hash] = date

        for line in lines:
            match = re.match(self.pattern, line)
            if match:
                date = match.group(1)
                user = match.group(2)
                message = match.group(3)
                ref = match.group(4)
                commit_hash = match.group(5)
                parent_hash1 = match.group(6)
                parent_hash2 = match.group(7)

                link = ""
                link2 = ""
                label_ext = ""
                node_message = ""
                if show_messages:
                    node_message = "\n" + message.replace("\"", "'")
                if commit_hash in predefined_node_color:
                    label_ext = "\\nSTASH INDEX"
                    node_color = predefined_node_color[commit_hash]

                else:
                    node_color = self.COLOR_NODE
                if parent_hash1:
                    link = " \"" + parent_hash1 + "\"->\"" + commit_hash + "\";"
                else:
                    # initial commit
                    node_color = self.COLOR_NODE_FIRST
                if parent_hash2:
                    link2 = " \"" + parent_hash2 + "\"->\"" + commit_hash + "\";"
                if parent_hash1 and parent_hash2:
                    node_color = self.COLOR_NODE_MERGE
                if message in messages:
                    # message exists in history - possible cherry-pick -> compare diff hashes
                    existing_hash = messages[message]
                    if commit_hash is not existing_hash and date > dates[existing_hash]:
                        diff_hash_old = self.get_commit_diff_hash(existing_hash)
                        diff_hash_actual = self.get_commit_diff_hash(commit_hash)
                        logging.debug("M [%s]", message)
                        logging.debug("1 [%s]", diff_hash_old)
                        logging.debug("2 [%s]", diff_hash_actual)
                        if diff_hash_old == diff_hash_actual:
                            logging.debug("equal")
                            digraph += '    "' + str(existing_hash) + '"->"' + \
                                       commit_hash + '"[label="Cherry\\nPick",style=dotted,' + \
                                       'fontcolor="red",color="red"]'
                            node_color = self.COLOR_NODE_CHERRY_PICK
                            # label_ext = "\\nCherry Pick"
                        logging.debug("")
                logging.debug("Message: [%s]", message)
                if message.startswith("Revert"):
                    # check for revert
                    logging.debug("Revert commit")
                    match = re.match(self.reverse_message_pattern, message)
                    if match:
                        original_message = match.group(1)
                        logging.debug("Revert match [%s]", original_message)
                        if original_message in messages:
                            orig_revert_hash = messages[original_message]
                            digraph += '    "' + commit_hash + '"->"' + str(orig_revert_hash) + \
                                       '"[label="Revert",style=dotted,fontcolor="azure4",' + \
                                       'color="azure4",constraint=false]'
                        else:
                            logging.warning('Not able to find the original revert ' +
                                            'commit for commit %s', commit_hash)
                            digraph += '    "revert_' + commit_hash + \
                                       '"[label="", shape=none, height=.0, width=.0]; "' + \
                                       commit_hash + '"->"revert_' + commit_hash + \
                                       '"[label="Revert ??",style=dotted,fontcolor="azure4",' + \
                                       'color="azure4"];'
                    node_color = self.COLOR_NODE_REVERT

                node_info = ""
                if ref:
                    ref_entries = ref.replace("(", "").replace(")", "").split(",")
                    for ref_entry in ref_entries:
                        style = "shape=oval,fillcolor=" + self.COLOR_BRANCH
                        if "HEAD" in ref_entry:
                            style = "shape=diamond,fillcolor=" + self.COLOR_HEAD
                        elif "tag" in ref_entry:
                            ref_entry = ref_entry.replace("tag: ", "")
                            style = "shape=oval,fillcolor=" + self.COLOR_TAG
                        elif "stash" in ref_entry:
                            style = "shape=box,fillcolor=" + self.COLOR_STASH
                            node_color = self.COLOR_STASH
                            label_ext = "\\nSTASH"
                            if self.get_commit_diff(parent_hash1) == "":
                                logging.debug('>>> "%s"[color=red]', parent_hash1)
                                predefined_node_color[parent_hash1] = self.COLOR_STASH
                            elif self.get_commit_diff(parent_hash2) == "":
                                logging.debug('>>> "%s"[color=red]', parent_hash2)
                                predefined_node_color[parent_hash2] = self.COLOR_STASH
                            continue
                        node_info += '    "' + ref_entry + '"[style=filled,' + style + ']; "' + \
                                     ref_entry + '" -> "' + commit_hash + '"\n'
                digraph += "    \"" + commit_hash + "\"[label=\"" + commit_hash + node_message + \
                           label_ext + "\\n(" + user + ")\",shape=box,style=filled,fillcolor=" + \
                           node_color + "];" + link + link2
                if node_info:
                    digraph += node_info
        digraph += "}"
        return digraph

    def get_html(self, filename, rev_range=None, log_options=None):
        """
        Write an html page
        :param rev_range: git commit range to deal with
        :param filename: html file name
        :param log_options: - dictionary containing other options to use for log command
                           - or None, in this case '-all' option is used
                           use an empty dictionary ([]) to suppress all options
        """
        svg = subprocess.run(['dot', '-Tsvg'],
                             input=self.get_dot(False, rev_range, log_options).encode('utf8'),
                             check=True, capture_output=True).stdout
        bodies = {}
        g_node = xml.dom.minidom.parseString(svg).getElementsByTagName("g")[0]
        for node in g_node.getElementsByTagName("g"):
            commit = node.getElementsByTagName("title")[0].childNodes[0].data
            if node.getAttribute("id").startswith('node'):
                # check=False because some nodes are not commits
                bodies[commit] = subprocess.run(['git', 'log', '-n1', commit], cwd=self.repository,
                                                capture_output=True,
                                                check=False).stdout.decode('utf-8')
                bodies[commit] = bodies[commit].replace("'", "&#39;").replace('\n', '<br/>')
                bodies[commit] = bodies[commit].replace('"', '&quot;')
                if self.url is not None:
                    bodies[commit] = re.sub(r'\b(' + commit + r'[a-z,0-9]*)\b',
                                            f"<a href='{self.url}/commit/{commit}'>\\1</a>",
                                            bodies[commit])

        # Html header
        html = '<!DOCTYPE html>\n'
        html += '<html>\n'
        html += '<head>\n'
#        html += '<meta charset="UTF-8">\n'
        html += '<meta http-equiv="content-type" content="text/html; charset=utf-8" />\n'
        html += '<title>Git commit diagram</title>\n'
        html += '<style>\n'
        html += """
.tooltip {
    position: absolute;
    white-space: nowrap;
    display: none;
    background: #ffffcc;
    border: 1px solid black;
    padding: 5px;
    z-index: 1000;
    color: black;
    text-align: right;
}
.tooltipHeader {
    color: red;
    border-bottom: 1px solid grey;
    margin-top: 0;
    margin-bottom: 0;
}
.tooltipContent {
    text-align: left;
    margin-top: 5px;
    margin-bottom: 0;
}
"""
        html += '</style>\n'

        html += '<script>\n'
        html += """
function moveTooltip(e) {
  if(! tooltip_is_fixed) {
    var x = (e.pageX + 20) + 'px',
        y = (e.pageY + 20) + 'px';
    tooltip.style.top = y;
    tooltip.style.left = x;
  }
}
var mouse_is_over=false;
var tooltip_is_fixed=false;
function overToolTip(e) {
  if(! tooltip_is_fixed) {
    var tooltipContent = document.getElementById('tooltipContent');
    tooltipContent.innerHTML = e.currentTarget.details;
    mouse_is_over=true;
    setTooltipVisibility();
  }
}
function outToolTip(e) {
  var tooltip = document.getElementById('tooltip');
  mouse_is_over=false;
  setTooltipVisibility();
}
function setTooltipVisibility() {
  if(mouse_is_over || tooltip_is_fixed) {
    tooltip.style.display = 'block';
  } else {
    tooltip.style.display = '';
  }
}
function clickTooltip(e) {
  tooltip_is_fixed=false;
  setTooltipVisibility();
}
function clickParentTooltip(e) {
  tooltip_is_fixed=false;
  moveTooltip(e);
  overToolTip(e);
  tooltip_is_fixed=true;
  setTooltipVisibility();
}

function addListeners() {
  var tooltips = document.querySelectorAll('.node');
  for(var i = 0; i < tooltips.length; i++) {
    tooltips[i].addEventListener('mousemove', moveTooltip);
    tooltips[i].addEventListener("mouseover", overToolTip);
    tooltips[i].addEventListener("mouseout", outToolTip);
    tooltips[i].addEventListener("click", clickParentTooltip);
    tooltips[i].details=logs[tooltips[i].getElementsByTagName("title")[0].innerHTML]
  }

  var tooltipHeader = document.getElementById('tooltipHeader');
  tooltipHeader.addEventListener('click', clickTooltip);
}

const logs = JSON.parse(`""" + json.dumps(bodies, indent=0) + """`);
"""
        html += '</script>\n'

        html += '</head>\n'
        html += "<body onload='addListeners()'>\n"

        # Tooltip
        html += '<span id="tooltip" class="tooltip">'
        html += '<p id="tooltipHeader" class="tooltipHeader">⨂</p>'
        html += '<p id="tooltipContent" class="tooltipContent">This is a tooltip<br/></p></span>'

        # SVG inclusion (with suppression of xml and doctype informations)
        svg = svg[svg.index(b'<svg'):]
        html += '<div>\n' + svg.decode('utf-8') + '\n</div>\n'

        # Html footer
        html += "</body>\n</html>"

        with open(filename, 'w', encoding='UTF-8') as f:
            f.write(html)

    def get_image(self, filename, show_messages=False, rev_range=None, log_options=None):
        """
        Write an image
        :param show_messages (optional): Show commit messages in node
        :param rev_range: git commit range to deal with
        :param filename: name of the image file to produce
                         The extension is used to determine the image format,
                         it must be one of the accepted agrument accepted on the
                         command line of the dot utility
                         See: https://www.graphviz.org/docs/outputs/
        :param log_options: - dictionary containing other options to use for log command
                           - or None, in this case '-all' option is used
                           use an empty dictionary ([]) to suppress all options
        """
        fmt = os.path.splitext(filename)[1][1:]
        if fmt == 'html':
            self.get_html(filename, rev_range, log_options)
        else:
            dot_command = ['dot', '-T' + fmt, '-o', filename]
            logging.info('Dot command: %s', ' '.join(dot_command))
            subprocess.run(dot_command,
                           input=self.get_dot(show_messages, rev_range, log_options).encode('utf8'),
                           check=True)


def main():
    """
    Function to deal with command line arguments
    """
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose", dest="verbose", action="count", default=0,
                        help="Show info messages on stderr or debug messages " +
                             "if -v option is set twice")
    parser.add_argument("-m", "--messages", dest="messages", action="store_true",
                        help="Show commit messages in node")
    parser.add_argument("-r", "--range", dest="range", default=None,
                        help="git commit range")
    parser.add_argument("-p", "--path", dest="path", default=None,
                        help="git repository to use (local directory or url)")
    parser.add_argument("-u", "--url", dest="url", default=None,
                        help="repository url to use in html output")
    parser.add_argument("-o", "--output", dest='output', default=None,
                        help="Image filename to produce, if not provided the DOT file will be " +
                             "outputed on STDOUT." +
                             "The extension is used to determine the image format, it must be " +
                             "one of the accepted agrument accepted on the command line of the " +
                             "dot utility (See: https://www.graphviz.org/docs/outputs/) + html")
    parser.add_argument('--option', dest='log_options', default=None, action='append',
                        help="Options to add to the 'git log' command used to find all the " +
                             "relevant commits. If no option is provided " +
                             "the '--all' option is used. Ex: --option=--remotes=upstream")

    args = parser.parse_args()
    if args.verbose > 0:
        level = 'INFO' if args.verbose == 1 else 'DEBUG'
        logging.basicConfig(level=getattr(logging, level, None))

    gg = Gitgraphz(args.path, args.url)
    if args.output is None or os.path.splitext(args.output)[1][1:] == 'dot':
        dot_content = gg.get_dot(show_messages=args.messages, rev_range=args.range,
                                 log_options=args.log_options)
        if args.output is None:
            print(dot_content)
        else:
            with open(args.output, 'w', encoding='UTF-8') as f:
                f.write(dot_content)
    else:
        gg.get_image(args.output, show_messages=args.messages, rev_range=args.range,
                     log_options=args.log_options)


if __name__ == '__main__':
    main()
