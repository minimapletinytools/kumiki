# Kumiki

Kumiki is a PROGRAMMATIC CAD library for timber framing and woodworking.

As a programmatic CAD tool, it is well suited for usage with AI agents 🤖

Kumiki is used together with Kigumi--a VSCode extension for viewing your kumiki designs!

Kumiki is in FREE and OPEN SOURCE (FOSS), try it out! There are many more features to come. 

![](tinyhouse120.png)

Expect frequent breaking changes accompanied by a minor version bump. Have your AI agent fix any borken frames due to API changes based on the changelog.

## setup

Kumiki is best used with Kigumi. Kigumi is available as a standalone app, or as a [VSCode extension](https://marketplace.visualstudio.com/items?itemName=minimaple.kigumi). There is also a [web beta version](https://kumiki.build/try/) with limited agent functionality if you just want to try it out. The standalone app with your own agent is the preferred way to use kigumi.

You can of course use Kumiki without Kigumi if you want to do that for some reason.

## your first kumiki project

Hit the new project button in kigumi or create a folder and open it. Then click "Initialize Project" in the kigumi side menu. Click "new frame" to create a new project file or ask your agent to make one for you.

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

## Drawing Support (BETA)

kumiki/kigumi supports generating drawings/plans/blueprints. There are 3 ways in general to create drawings:

- algorithmically generated drawings
- coded drawings
- manually added drawings

Ask your agent to add drawings to your file to get start. To manually add your own drawings, open the drawing you want to modify and select the features you want to measure from, hit the measure button or "m" and then select the feature to measure to. If there are no drawings, you can create one by selecting the timber(s) you want to draw and hit "draw timber" or you can generate a drawing of your entire frame by pressning "draw frame" when nothing is selected.

You can also export as STEP or STL files to generate drawings in another software.

# Contributing

If you'd like to contribute new joints, you can always create a new file in kumiki/joints/community and add yourself as a CODEOWNER for that file. These joints may eventually be promoted to the main joint folder. 

If you'd like to contribute it's best to first contact me. There are plenty of joints and new features to work on :).

## Developing Kigumi

Kigumi is 100% AI SLOP and it seems to not even be that awful :). Still, it's designed with more care than I might sometimes pretends. It may be best to open a bug report of feature request in github vs making a PR as I have no documented architectural guidance for kigumi yet simultaneously highly opinionated. Pull requests that change anything under `kigumi/` need a signed [Contributor License Agreement](CLA.md) before they can be merged. The CLA bot asks on your first such PR and tells you exactly what to comment; you only sign once. Contributions to kumiki need no CLA.

# License

- **kumiki** (the Python library, its patterns and docs) is under the [Mozilla Public License 2.0](LICENSE).
- **kigumi** (the viewer: the VS Code extension and desktop app, in `kigumi/`) is under the [Elastic License 2.0](kigumi/LICENSE). You may use, modify and redistribute it freely, including commercially. What you may not do is offer it to others as a hosted or managed service -- the hosted web version of kigumi is published only by the project owner.

Releases of kigumi up to and including 0.7.2 were under MPL-2.0 and remain so. Third-party files bundled with kigumi, such as those in `kigumi/webview/vendor/`, keep their own licenses.
