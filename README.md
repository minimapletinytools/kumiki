# Kumiki

Kumiki is a Code aided Design (CoAD) library for programmatically designing timber framed structures and woodworking in general.

As Kumiki is a CoAD library, it is well suited for usage with AI agents.

Kumiki is used together with Kigumi--a VSCode extension for viewing your kumiki designs!

## setup

Kumiki is best used with Kigumi. To install Kigumi, install [VSCode](https://code.visualstudio.com/) and install the [Kigumi](https://marketplace.visualstudio.com/items?itemName=minimaple.kigumi) extension.

I think Kigumi also requires [python3](https://www.python.org/downloads/), the rest of the dependencies get installed automagically for you.

You can of course use Kumiki without Kigumi. You can still use Kigumi to setup your Kumiki projects and its dependencies.

## your first kumiki project

Create a folder for your Kumiki project and open that folder in VSCode. Then click "Initialize Project" from the Kumiki menu. You may also run "kigumi: initialize project" command from the command pallete. This will create a placeholder MyCuteFrame.py project file for you that you can build on! 

Open the Kigumi menu by clicking on the Kigumi extension icon in the left side bar.
You may also open Kigumi by opening the command palette in VScode (cmd/ctrl+shift+p). Start typing "kigumi" and choose the "View: Show Kigumi" command. 
You can open a Kumiki project file directly by choosing "Kigumi: Open Current File in Viewer" in the command pallete when that file is focused.

## viewing the built in patterns and examples

Kigumi ships with a patternbook and several examples. These can be explored through the kigumi menu. You can choose to "view source" or "duplicate in workspace" if you want to modify the patterns.

## making changes

Kigumi installs with a set of AI agent instructions and skills, and the AI agent has access to the entire Kumiki source code so it more or less knows to how to write Kumiki designs. Using human like prompting should serve you pretty well. Please refer to the patternbook for the list of available joints. It's best to build your structure in increments previewing each step along the way but I won't stop you from asking your agent to "build me a house".

You can implement your own joints as well but AI agents currently struggle with this so don't expect much.

Understanding Kumiki will allow you to better pilot the AI agent to implement your designs. Please see the docs folder to learn more about Kumiki's designs. You can of course implement your designs yourself too!

Someday I'll have better prompting examples and skills to share here. Stay tuned.

# Contributing

There are many many more feature, resources and examples I'd like to add to Kumiki/Kigumi! You are welcome to open issues or make PRs to update Kumiki. Unfortunately I do not have any contribution guidelines ready so you may want to reach out to me before making any changes. 

## Developing Kumiki

To setup for local development, just check out this repo and use `uv` to manage all your dependencies. The `Makefile` has convenient shortcuts for all your setup and testing needs.

Kigumi has a separate project scanning flow such that it can be used with the Kumiki repo itself as the workspace. Just use Kigumi like you normally would to test Kumiki.

## Developing Kigumi

TODO



# APPENDIX

## FreeCAD and Fusion360 usage

Rendering in FreeCAD and Fusion360 currently requires checking out the entire repo. We do not plan to work around this and support for these tools will be removed soon. 
