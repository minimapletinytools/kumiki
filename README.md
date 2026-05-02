# Kumiki

Kumiki is a Code aided Design (CoAD) library for programmatically designing timber framed structures and woodworking in general.

As Kumiki is a CoAD library, it is well suited for usage with AI agents.

Kumiki is used together with Kigumi--a VSCode extension for viewing your kumiki designs!


INSTRUCTIONS BELOW DO NOT WORK YET DO NOT TRY!!!

## setup

## local development

If you are working in this repository directly, you can import and run Kumiki from the repo without installing from PyPI.

If you are working in a separate project and want to use the latest Kumiki code from git, install it from GitHub:

```bash
pip install "git+https://github.com/minimaple/kumiki.git"
```

For a pinned revision, append a commit, branch, or tag:

```bash
pip install "git+https://github.com/minimaple/kumiki.git@<ref>"
```

Kumiki is best used with Kigumi. To install Kigumi, download [VSCode](https://code.visualstudio.com/) and install Kigumi (TODO link)

Kumiki also requires [python3](https://www.python.org/downloads/).  

You can of course use Kumiki withou Kigumi. You will still want to use Kigumi to setup your Kumiki projects and its dependencies.

## viewing the built in patterns and examples

Kigumi ships with a patternbook and several examples. Open the Kumiki menu by clicking on the Kumiki horse icon in the bar on the left side and click "Open Kigumi".

You may also open Kigumi by opening the command palette in VScode (cmd/ctrl+shift+p). Start typing "kigumi" and choose the "kigumi: open" command.

## your first kumiki project

Create a folder for your Kumiki project and open that folder in VSCode. Then click "Initialize Project" from the Kumiki menu. You may also run "kigumi: initialize project" command from the command pallete.

TODO finish

## for advanced students

TODO finish


# Contributing

If making changes to Kumiki itself, a separate workflow is used. 

Once you've made your changes, open up a PR. 


## Developing Kumiki

TODO

Kigumi has a separate project scanning flow such that it can be used with the Kumiki repo itself as the workspace. Just use Kigumi like you normally would to test Kumiki.

## Developing Kigumi

TODO


# APPENDIX

## FreeCAD and Fusion360 usage

Rendering in FreeCAD and Fusion360 currently requires checking out the entire repo. We do not plan to work around this and support for these tools will be removed soon. 
