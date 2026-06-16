# Kumiki

Kumiki is a Code assisted Design (CoAD) library for programmatically designing timber framed structures and woodworking in general.

As Kumiki is a CoAD library, it is well suited for usage with AI agents.

Kumiki is used together with Kigumi--a VSCode extension for viewing your kumiki designs!

## setup

Kumiki is best used with Kigumi. To install Kigumi, install [VSCode](https://code.visualstudio.com/) and install the [Kigumi](https://marketplace.visualstudio.com/items?itemName=minimaple.kigumi) extension.

I think Kigumi also requires [python3](https://www.python.org/downloads/), the rest of the dependencies get installed automagically for you.

You can of course use Kumiki without Kigumi. You can still use Kigumi to setup your Kumiki projects and its dependencies.

## your first kumiki project

Create a folder for your Kumiki project and open that folder in VSCode. Then click "Initialize Project" from the Kumiki menu. You may also run "kigumi: initialize project" command from the command pallete. This will create a placeholder my_cute_frame.py project file for you that you can build on! 

Open the Kigumi menu by clicking on the Kigumi extension icon in the left side bar.
You may also open Kigumi by opening the command palette in VScode (cmd/ctrl+shift+p). Start typing "kigumi" and choose the "View: Show Kigumi" command. 
You can open a Kumiki project file directly by choosing "Kigumi: Open Current File in Viewer" in the command pallete when that file is focused.

## viewing the built in patterns and examples

Kigumi ships with a patternbook and several examples. These can be explored through the kigumi menu. You can choose to "view source" or "duplicate in workspace" if you want to modify the patterns. 

## making changes

Kigumi designs are built with CODE. You can write this CODE yourself, or you can ask AI to write the CODE for you.

Kigumi installs with a set of AI agent instructions. The installed `kumiki` Python package includes the Kumiki library source files, built-in patterns, and the `docs/` content, so those resources are present in the Python environment used by Kigumi. Using human like prompting should serve you pretty well. Using carpentry or woodworknig terminology will serve you better. Please refer to the patternbook for the list of available joints. It's best to build your structure in increments previewing each step along the way but I won't stop you from asking your agent to "build me a house". You can implement your own joints as well. The AI agents currently struggle with this especially if you are unfamiliar with terminology and geometry conventions for prompting it, so don't expect much. Someday I'll have better prompting examples and skills to share here. Stay tuned.

To learn more about authoring Kumiki designs without AI, please start with [docs/concepts.md](docs/concepts.md) to learn more about Kumiki's design philosophy, and then proceed with the various example structures that ship with Kumiki.
Kumiki is very SIMPLE and VERBOSE by design. So it LOOKS complex but in actuality, it is quite simple to understand. A typical structure is built as follows:

- estabalish a footprint
- erect foundational timbers on the footprint
- join foundational timbers with additional timbers to complete the "shape" of the structure
- cut joints on timbers to properly connect the timbers completing the structure

Understanding Kumiki will also allow you to better instruct the agent to implement your designs! For example, instead of saying "I want my building to be an L shape" you might say "establish an L shaped footprint for the building". If you ever have questions, you can also just ask the agent to explain!

## Drawing Support

To generate drawings, your best bet right now is to export as STEP or STL files and generate drawings in another software. Kumiki/Kigumi will add support for this in 3 stages:

1. ability to measure features relative to each other in Kigumi
2. ability to generate and export drawings inside kigumi


## Developing Kumiki

To setup for local development, just check out this repo and use `uv` to manage all your dependencies. The `Makefile` has convenient shortcuts for all your setup and testing needs.

Kigumi has a separate project scanning flow such that it can be used with the Kumiki repo itself as the workspace. Just use Kigumi like you normally would to test Kumiki.

## Developing Kigumi

TODO


## FreeCAD and Fusion360 usage

Rendering in FreeCAD and Fusion360 currently requires checking out the entire repo. We do not plan to work around this and support for these tools will be removed soon. 
