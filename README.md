# git-graphz

Tool to create a graph from a git history showing tags, branches, stash nodes, cherry-picks.

Full documentation available [online](https://sebastienriettemto.github.io/git-graphz/)

## Requirements

* Python3
* Graphiz (only to convert DOT format to an image)

## Create a graph

Run the following inside a git directory to write a graph description (DOT format) to stdout.

    git-graphz

On linux you can use the following command to create a graph.ps file

    git-graphz | dot -Tps -o graph.ps

Or you can simply (the file extension must be an accepted command line option of the dot utility (see [here](https://www.graphviz.org/docs/outputs/))

    git-graphz -o image.pdf

In addition to the graphviz accepted extensions, it is also possible to generate an html page

    git-graphz -o image.html

Example with range

    git-graphz -r a51eced..HEAD | dot -Tps -o graph.ps

Example with upstream commits

    git-graphz --option=--remotes=upstream

You can also provide an url for the git repository (instead of running the command in a git directory)

    git-graphz -p https://github.com/SebastienRietteMTO/git-graphz.git

### Parameters
* **-v**: to print info (or debug if provided twice) output to stderr
* **-m**: show commit messages in nodes
* **-r range**: to get a specific range of the repository. See [here](http://git-scm.com/book/en/Git-Tools-Revision-Selection#Commit-Ranges)
* **-p path**: to specify the directory containig the git repository (current working directory if omitted) or the url of a git repository
* **--option=OPTION**: to add an option to the git log command used to list the relevant commits. If no option is provided the '--all' option is used. Ex: --option=--remotes=upstream

# Example Graphs
--> [Current git graph](current_tree.html) <--


![simple example](docs/example.gif)
