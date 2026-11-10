<h1 align="center">Kumiki</h1>

<p align="center">
  <b>Programmatic CAD for timber framing and woodworking.</b><br>
  Design frames and joinery in Python, and see them in 3D with Kigumi.
</p>

<p align="center">
  <a href="https://github.com/minimapletinytools/kumiki/releases">Releases</a> ·
  <a href="https://kumiki.build/try/">Try it online</a> ·
  <a href="https://kumiki.build">Website</a> ·
  <a href="https://kumiki.build/docs/">Docs</a> ·
  <a href="https://github.com/minimapletinytools/kumiki/discussions">Discussions</a> ·
  <a href="https://discord.gg/cQhUG7WJ8">Discord</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/kumiki/"><img alt="PyPI" src="https://img.shields.io/pypi/v/kumiki?label=kumiki"></a>
  <a href="https://marketplace.visualstudio.com/items?itemName=minimaple.kigumi"><img alt="Kigumi" src="https://img.shields.io/open-vsx/v/minimaple/kigumi?label=kigumi"></a>
  <a href="https://github.com/minimapletinytools/kumiki/actions/workflows/pytest.yml"><img alt="Tests" src="https://github.com/minimapletinytools/kumiki/actions/workflows/pytest.yml/badge.svg"></a>
  <a href="https://discord.gg/cQhUG7WJ8"><img alt="Discord" src="https://img.shields.io/badge/discord-join-5865F2?logo=discord&logoColor=white"></a>
</p>

![A tiny house frame designed in Kumiki](tinyhouse120.png)

kumiki is a **programmatic** CAD library for timber framing and woodworking. Designs are written as programs which are flexible, parametric, and precise.

Because designs are code, Kumiki works well with AI agents 🤖. Agents are good at using tools but even better at writing code.

kigumi is the standalone viewer app for viewing kumiki frames and plans and also serves as a development environment.

> [!NOTE]
> kumiki is under active development. Minor version bumps may result in breaking changes, Your agent can easily fix any frames that break due to suc upgrades based on the [changelog](CHANGELOG.md).

## Features

- **Parametric joinery.** Dozens of joints (mortise and tenon, dovetails, laps, scarfs, pegs,
  wedges and more), each parametrically sized to the timbers it joins.
- **Examples and Patterns** Extensive examples and patterns to explore what's possible and provide one-shot learning for your AI agent.
- **3D renders in Kigumi.** Select down to a face, walk a joint's CSG tree, use X-ray and
  section views, and measure.
- **Drawings (beta).** Plans and dimensioned shop drawings, so you can permit and actually build your designs.
- **Dissamblies (beta).** Kumiki works out the order a frame goes together, and plays it back.
- **Export.** STL, OBJ, 3MF and STEP.
- **Built for agents.** Kigumi installs agent instructions with each project, has an agent of its
  own, and an MCP server so your agent can see what it built.

## Get started

kumiki is used with the **kigumi** viewer:

| | |
|---|---|
| **Desktop app** (recommended) | Mac and Windows, from the [releases page](https://github.com/minimapletinytools/kumiki/releases) or [kumiki.build/install](https://kumiki.build/install). Use it with your own agent. |
| **VS Code extension** | From the [Marketplace](https://marketplace.visualstudio.com/items?itemName=minimaple.kigumi), or [Open VSX](https://open-vsx.org/extension/minimaple/kigumi) for Cursor. |
| **In your browser** (beta) | [kumiki.build/try](https://kumiki.build/try/). Nothing to install, with a limited agent: good for a first look. Token subscriptions coming soon. |

### Your first project

In the app, click **New Project** and pick a folder. In VS Code, open a folder and click
**Initialize Project** in the Kigumi sidebar. Then click **New Frame…** at the bottom of the frames
list.

OR set up the MCP and ask your agent to setup the project for you (see below)

### Patterns and examples

Kumiki ships with a pattern book of joints and several example frames, listed in Kigumi's
explorer. Choose **View Source** to read one, or **Duplicate to Workspace** to make your own copy.

## Designing frames

Kumiki designs are built with code. You can write it yourself, or ask an agent to write it for
you.

### With an agent

Open your coding agent in your kigumi project folder. It's also good idea to connect your agent to the kigumi MCP.

Plain prompts work well, and carpentry and woodworking terms work better. See the pattern book for
the joints available. The agent can implement its own custom joints too! It's best to build a structure in steps, previewing each one and modifying as you go. No one can stop youfrom asking your agent to "build me a house". 

#### Connecting your agent to the kigumi MCP

The kigumi MCP (model context protocol) exposes kigumi functionality to your agent so it can manage your project and preview your frames for automation. 

To setup the MCP expand the "MCP" row in the left file explorer and make sure "enable MCP server for agents" is checked. Then copy for your agent. If you're unsure, just copy the "URL and token" option and ask your agent to connect to it.

#### How does it work? 

kigumi projects install with a set of [agent usage instructions](docs/agent_usage_instructions.md) and an
[API cheat sheet](docs/api_cheat_sheet.md) and the entire `kumiki` library source is available as well so the agent so your agent has everything it needs!


### By hand

Start with [docs/concepts.md](docs/concepts.md) for Kumiki's design philosophy, then read the
example frames that ship with it. Kumiki is simple and verbose by design: it *looks* complex, but
each step is easy to follow. A typical structure is built like this:

1. Establish a footprint.
2. Raise foundational timbers on the footprint.
3. Join them with more timbers to complete the structure's shape.
4. Cut joints where the timbers meet.

Knowing these steps helps you direct an agent, too. Instead of "I want my building to be an L
shape", try "establish an L-shaped footprint for the building". And if you have questions, ask
the agent to explain.

## Drawings (beta)

Kumiki and Kigumi make drawings, plans and blueprints in three ways:

- **Generated** from the frame using `with_auto_drawings`.
- **Coded** one at a time in your frame file.
- **Added manually** in Kigumi.

Ask your agent to add drawings to your file to get started. To add a dimension by hand, open a
drawing, select the feature to measure from, press the measure button (or <kbd>M</kbd>) and select
the feature to measure to. With no drawings yet, select timbers and press **draw timber**, or
press **draw frame** with nothing selected to draw the whole frame.

You can also export STEP or STL files and make drawings in other software.

## Community

- **Questions and ideas:** [GitHub Discussions](https://github.com/minimapletinytools/kumiki/discussions)
- **Chat:** [Discord](https://discord.gg/cQhUG7WJ8)
- **Bugs and feature requests:** [Issues](https://github.com/minimapletinytools/kumiki/issues)

## Contributing

To contribute a new joint, add a file in `kumiki/joints/community` and add yourself as its
CODEOWNER. Community joints may later be promoted to the main joint folder.

For anything bigger, please get in touch first. There is plenty of work to be done :).

Low effort vibe coded PRs will likely be ignored. Just open an issue instead if you're not wanting to understand the code. I have tokens to spare.

### Developing Kigumi

Kigumi is written almost entirely with AI coding agents, under close direction. There's no written
architecture guide yet, and its design is opinionated, so a bug report or feature request is often
better than a pull request.

Pull requests that change anything under `kigumi/` need a signed
[Contributor License Agreement](CLA.md). The CLA bot asks on your first such PR and tells you what
to comment; you only sign once. Contributions to kumiki need no CLA.

## License

- **kumiki** (the Python library, its patterns and docs) is under the
  [Mozilla Public License 2.0](LICENSE).
- **kigumi** (the viewer: the VS Code extension and desktop app, in `kigumi/`) is under the
  [Elastic License 2.0](kigumi/LICENSE). You may use, modify and redistribute it freely, including
  commercially. You may not offer it to others as a hosted or managed service: the hosted web
  version of kigumi is published only by the project owner.

Releases of kigumi up to and including 0.7.2 were under MPL-2.0 and remain so. Third-party files
bundled with kigumi, such as those in `kigumi/webview/vendor/`, keep their own licenses.
