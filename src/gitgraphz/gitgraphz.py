#!/usr/bin/python3

__author__ = 'Stephan Bechter <stephan@apogeum.at>'
__version__ = '1.1.0'

import subprocess
import re
import hashlib
import sys
import logging
import os
import tempfile

class Gitgraphz():
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
            self._tmpdir = tempfile.TemporaryDirectory() #will be deleted when self._tmpdir will be garbage collected
            self.repository = self._tmpdir.name
            command = ['git', 'clone', repository, '.']
            logging.info('Git command: ' + ' '.join(command))
            status = subprocess.run(command, cwd=self.repository).returncode
            if status != 0:
                raise RuntimeError("Error during repository cloning using the url: " + str(repository))
        if self.url is not None and not self.url.startswith('https://'):
            self.url = None
        command = ['git', 'rev-parse']
        logging.info('Git command: ' + ' '.join(command))
        status = subprocess.run(command, cwd=self.repository).returncode
        if status != 0:
            if repository is None:
                message = "It seems that current working directory is not inside a git repository!"
            else:
                message = "It seems that this directory ({repository}) is not a git repository!".format(repository=repository)
            raise RuntimeError(message)

        self.pattern = re.compile(r'^\[(\d+)\|\|(.*)\|\|(.*)\|\|\s?(.*)\]\s([0-9a-f]*)\s?([0-9a-f]*)\s?([0-9a-f]*)$')
        self.revertMessagePattern = re.compile(r'Revert "(.*)"')

    def getLog(self, revRange=None, options=None):
        """
        :param revRange: git commit range to deal with
        :param options: - dictionary containing other options to use for log command
                        - or None, in this case '--all' option is used
                        use an empty dictionary ([]) to suppress all options
        """
        if revRange is not None:
            logging.info("Range: " + revRange)
            revRange = [revRange]
        else:
            revRange = []
        if options is None:
            options = ['--all']
        gitLogCommand = ['git', 'log', '--pretty=format:[%ct||%cn||%s||%d] %h %p'] + options + revRange
        logging.info('Git log command: ' + ' '.join(gitLogCommand))
        out = subprocess.run(gitLogCommand, cwd=self.repository, capture_output=True,
                             universal_newlines=True, check=True).stdout.split('\n')
        return out

    def getCommitDiff(self, hash):
        command = ['git', 'diff', hash + '^', hash]
        logging.debug("Hash Command: " + ' '.join(command))
        diff = subprocess.run(command, cwd=self.repository, capture_output=True, check=True).stdout
        # get only the changed lines (starting with + or -), no line numbers, hashes, ...
        diff = b'\n'.join([l for l in diff.splitlines() if (l.startswith(b'+') or l.startswith(b'-'))])
        return diff
    
    def getCommitDiffHash(self, hash):
        diff = self.getCommitDiff(hash)
        sha = hashlib.sha1(diff)
        return sha.hexdigest()

    def getDot(self, showMessages=False, revRange=None, logOptions=None):
        """
        :param showMessages (optional): Show commit messages in node
        :param revRange (optional): git commit range to deal with
        :param logOptions: - dictionary containing other options to use for log command
                           - or None, in this case '-all' option is used
                           use an empty dictionary ([]) to suppress all options
        """
        lines = self.getLog(revRange, logOptions)
        
        dates = {}
        messages = {}
        predefinedNodeColor = {}
        
        digraph = "digraph G {"
        #first extract messages
        for line in lines:
            match = re.match(self.pattern, line)
            if match:
                date = match.group(1)
                message = match.group(3)
                commitHash = match.group(5)
                if message in messages:
                    existing = messages[message]
                    #print(dates[existing]+" - "+date)
                    if dates[existing] > date:
                        #print("setting message ["+message+"] with ["+hash+"]")
                        messages[message] = commitHash
                else:
                    messages[message] = commitHash
                dates[commitHash] = date
        
        for line in lines:
            #print(line)
            match = re.match(self.pattern, line)
            if match:
                date = match.group(1)
                user = match.group(2)
                message = match.group(3)
                ref = match.group(4)
                commitHash = match.group(5)
                parentHash1 = match.group(6)
                parentHash2 = match.group(7)
        
                link = ""
                link2 = ""
                labelExt = ""
                nodeMessage = ""
                if showMessages:
                    nodeMessage = "\n" + message.replace("\"", "'");
                if commitHash in predefinedNodeColor:
                    labelExt = "\\nSTASH INDEX"
                    nodeColor = predefinedNodeColor[commitHash]
        
                else:
                    nodeColor=self.COLOR_NODE
                if parentHash1:
                    link = " \"" + parentHash1 + "\"->\"" + commitHash + "\";"
                else:
                    #initial commit
                    nodeColor = self.COLOR_NODE_FIRST
                if parentHash2:
                    link2 = " \"" + parentHash2 + "\"->\"" + commitHash + "\";"
                if parentHash1 and parentHash2:
                    nodeColor = self.COLOR_NODE_MERGE
                if message in messages:
                    # message exists in history - possible cherry-pick -> compare diff hashes
                    existingHash = messages[message]
                    if commitHash is not existingHash and date > dates[existingHash]:
                        diffHashOld = self.getCommitDiffHash(existingHash)
                        diffHashActual = self.getCommitDiffHash(commitHash)
                        logging.debug("M [" + message + "]")
                        logging.debug("1 [" + diffHashOld + "]")
                        logging.debug("2 [" + diffHashActual + "]")
                        if diffHashOld == diffHashActual:
                            logging.debug("equal")
                            digraph += '    "' + str(existingHash) + '"->"' + commitHash + '"[label="Cherry\\nPick",style=dotted,fontcolor="red",color="red"]'
                            nodeColor = self.COLOR_NODE_CHERRY_PICK
                            #labelExt = "\\nCherry Pick"
                        logging.debug("")
                logging.debug("Message: [" + message + "]")
                if message.startswith("Revert"):
                    # check for revert
                    logging.debug("Revert commit")
                    match = re.match(self.revertMessagePattern, message)
                    if match:
                        originalMessage = match.group(1)
                        logging.debug("Revert match [" + originalMessage + "]")
                        if originalMessage in messages:
                            origRevertHash = messages[originalMessage]
                            digraph += '    "' + commitHash + '"->"' + str(origRevertHash) + '"[label="Revert",style=dotted,fontcolor="azure4",color="azure4",constraint=false]'
                        else:
                            logging.warning('Not able to find the original revert commit for commit ' + commitHash)
                            digraph += '    "revert_' + commitHash + '"[label="", shape=none, height=.0, width=.0]; "' + commitHash + '"->"revert_' + commitHash + '"[label="Revert ??",style=dotted,fontcolor="azure4",color="azure4"];'
                    nodeColor = self.COLOR_NODE_REVERT
        
                nodeInfo = ""
                if ref:
                    refEntries = ref.replace("(", "").replace(")", "").split(",")
                    for refEntry in refEntries:
                        style = "shape=oval,fillcolor=" + self.COLOR_BRANCH
                        if "HEAD" in refEntry:
                            style = "shape=diamond,fillcolor=" + self.COLOR_HEAD
                        elif "tag" in refEntry:
                            refEntry = refEntry.replace("tag: ", "")
                            style = "shape=oval,fillcolor=" + self.COLOR_TAG
                        elif "stash" in refEntry:
                            style = "shape=box,fillcolor=" + self.COLOR_STASH
                            nodeColor = self.COLOR_STASH
                            labelExt = "\\nSTASH"
                            if self.getCommitDiff(parentHash1) == "":
                                logging.debug('>>> "' + parentHash1 + '"[color=red]')
                                predefinedNodeColor[parentHash1] = self.COLOR_STASH
                            elif self.getCommitDiff(parentHash2) == "":
                                logging.debug('>>> "' + parentHash2 + '"[color=red]')
                                predefinedNodeColor[parentHash2] = self.COLOR_STASH
                            continue
                        #else:
                            #if "origin" in refEntry:
                            #    continue
                        nodeInfo += '    "' + refEntry + '"[style=filled,' + style + ']; "' + refEntry + '" -> "' + commitHash + '"\n'
                digraph += "    \"" + commitHash + "\"[label=\"" + commitHash + nodeMessage + labelExt + "\\n(" + user + ")\",shape=box,style=filled,fillcolor=" + nodeColor + "];" + link + link2
                if nodeInfo:
                    digraph += nodeInfo
        digraph += "}"
        return digraph

    def getHtml(self, filename, revRange=None, logOptions=None):
        """
        Write an html page
        :param revRange: git commit range to deal with
        :param filename: html file name
        :param logOptions: - dictionary containing other options to use for log command
                           - or None, in this case '-all' option is used
                           use an empty dictionary ([]) to suppress all options
        """

        import xml.dom.minidom
        import json
        
        svg = subprocess.run(['dot', '-Tsvg'], input=self.getDot(False, revRange, logOptions).encode('utf8'),
                             check=True, capture_output=True).stdout
        bodies = {}
        for node in xml.dom.minidom.parseString(svg).getElementsByTagName("g")[0].getElementsByTagName("g"):
            commit = node.getElementsByTagName("title")[0].childNodes[0].data
            if node.getAttribute("id").startswith('node'):
                #check=False because some nodes are not commits
                bodies[commit] = subprocess.run(['git', 'log', '-n1', commit], cwd=self.repository, 
                                                capture_output=True, check=False).stdout.decode('utf-8')
                bodies[commit] = bodies[commit].replace("'", "&#39;").replace('\n', '<br/>').replace('"', '&quot;')
                if self.url is not None:
                    bodies[commit] = re.sub(r'\b(' + commit + r'[a-z,0-9]*)\b', f"<a href='{self.url}/commit/{commit}'>\\1</a>", bodies[commit])

        #Html header
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

        #Tooltip
        html += '<span id="tooltip" class="tooltip"><p id="tooltipHeader" class="tooltipHeader">⨂</p><p id="tooltipContent" class="tooltipContent">This is a tooltip<br/></p></span>'

        #SVG inclusion (with suppression of xml and doctype informations)
        svg = svg[svg.index(b'<svg'):]
        html += '<div>\n' + svg.decode('utf-8') + '\n</div>\n'

        #Html footer
        html += "</body>\n</html>"

        with open(filename, 'w') as f:
          f.write(html)

    def getImage(self, filename, showMessages=False, revRange=None, logOptions=None):
        """
        Write an image
        :param showMessages (optional): Show commit messages in node
        :param revRange: git commit range to deal with
        :param filename: name of the image file to produce
                         The extension is used to determine the image format,
                         it must be one of the accepted agrument accepted on the
                         command line of the dot utility
                         See: https://www.graphviz.org/docs/outputs/
        :param logOptions: - dictionary containing other options to use for log command
                           - or None, in this case '-all' option is used
                           use an empty dictionary ([]) to suppress all options
        """
        fmt = os.path.splitext(filename)[1][1:]
        if fmt == 'html':
            self.getHtml(filename, revRange, logOptions)
        else:
            dotCommand = ['dot', '-T' + fmt, '-o', filename]
            logging.info('Dot command: ' + ' '.join(dotCommand))
            subprocess.run(dotCommand, input=self.getDot(showMessages, revRange, logOptions).encode('utf8'), check=True)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    
    parser.add_argument("-v", "--verbose", dest="verbose", action="count", default=0,
                        help="Show info messages on stderr or debug messages if -v option is set twice")
    parser.add_argument("-m", "--messages", dest="messages", action="store_true", help="Show commit messages in node" )
    parser.add_argument("-r", "--range", dest="range", default=None, help="git commit range" )
    parser.add_argument("-p", "--path", dest="path", default=None, help="git repository to use (local directory or url)")
    parser.add_argument("-u", "--url", dest="url", default=None, help="repository url to use in html output")
    parser.add_argument("-o", "--output", dest='output', default=None,
                        help="Image filename to produce, if not provided the DOT file will be outputed on STDOUT." + \
                             "The extension is used to determine the image format, it must be one of the accepted agrument accepted on the " + \
                             "command line of the dot utility (See: https://www.graphviz.org/docs/outputs/) + html")
    parser.add_argument('--option', dest='logOptions', default=None, action='append',
                        help="Options to add to the 'git log' command used to find all the relevant commits. If no option is provided " + \
                             "the '--all' option is used. Ex: --option=--remotes=upstream")
    
    args = parser.parse_args()
    if args.verbose > 0:
        level = 'INFO' if args.verbose == 1 else 'DEBUG'
        logging.basicConfig(level=getattr(logging, level, None))

    gg = Gitgraphz(args.path, args.url)
    if args.output is None or os.path.splitext(args.output)[1][1:] == 'dot':
        dotContent = gg.getDot(showMessages=args.messages, revRange=args.range, logOptions=args.logOptions)
        if args.output is None:
            print(dotContent)
        else:
            with open(args.output, 'w') as f:
                f.write(dotContent)
    else:
        gg.getImage(args.output, showMessages=args.messages, revRange=args.range, logOptions=args.logOptions)

if __name__ == '__main__':
    main()

