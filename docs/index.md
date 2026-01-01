---
title: Home
---

# PyView

<img src="https://pyview.rocks/images/pyview_logo_512.png" width="128px" align="right" />

PyView brings the [Phoenix LiveView](https://github.com/phoenixframework/phoenix_live_view) paradigm to Python: build dynamic, real-time web applications using server-rendered HTML.
## Quick Start

```bash
cookiecutter gh:ogrodnek/pyview-cookiecutter
```

Or try a [single-file app](single-file-apps.md) with zero setup.

## Live Examples

See PyView in action: [examples.pyview.rocks](https://examples.pyview.rocks/)

## Documentation

### Getting Started

- **[Getting Started](getting-started.md)** — Installation, first app, project structure

### Core Concepts

- **[LiveView Lifecycle](core-concepts/liveview-lifecycle.md)** — mount, handle_event, handle_params, handle_info
- **[Socket and Context](core-concepts/socket-and-context.md)** — State management, pub/sub, navigation
- **[Event Handling](core-concepts/event-handling.md)** — Clicks, forms, typed parameters, decorators
- **[Live Components](core-concepts/live-components.md)** — Stateful, reusable UI components (Python 3.14+)
- **[Routing](core-concepts/routing.md)** — URL patterns, path parameters, route organization

### Templating

- **[Overview](templating/overview.md)** — Choose your templating approach
- **[HTML Templates](templating/html-templates.md)** — Jinja2-like syntax with .html files
- **[T-String Templates](templating/t-string-templates.md)** — Python 3.14+ inline templates

### Features

- **[File Uploads](features/file-uploads/index.md)** — Direct and external (S3) uploads
- **[Streams](streams-usage.md)** — Efficient rendering of large collections
- **[Sessions & Authentication](features/authentication.md)** — Login, sessions, protected routes
- **[Single-File Apps](single-file-apps.md)** — Quick prototypes with PEP 723

## Example Projects

- [pyview-example-ai-chat](https://github.com/pyview/pyview-example-ai-chat) — AI chat with streaming responses
- [pyview-example-auth](https://github.com/pyview/pyview-example-auth) — Authentication with authlib

## Source Code

[github.com/ogrodnek/pyview](https://github.com/ogrodnek/pyview)
