from typing import Callable, Optional, TypedDict

from markupsafe import Markup


class RootTemplateContext(TypedDict):
    id: str
    content: str
    title: Optional[str]
    csrf_token: str
    session: Optional[str]
    additional_head_elements: list[Markup]


RootTemplate = Callable[[RootTemplateContext], str]
ContentWrapper = Callable[[RootTemplateContext, Markup], Markup]


def defaultRootTemplate(
    css: Optional[Markup] = None,
    content_wrapper: Optional[ContentWrapper] = None,
    title: Optional[str] = None,
    title_suffix: Optional[str] = " | LiveView",
) -> RootTemplate:
    content_wrapper = content_wrapper or (lambda c, m: m)

    def template(context: RootTemplateContext) -> str:
        return _defaultRootTemplate(
            context, css or Markup(""), content_wrapper, title, title_suffix
        )

    return template


def _defaultRootTemplate(
    context: RootTemplateContext,
    css: Markup,
    contentWrapper: ContentWrapper,
    default_title: Optional[str] = None,
    title_suffix: Optional[str] = " | LiveView",
) -> str:
    suffix = title_suffix or ""
    # Use context title if provided, otherwise use default_title, otherwise "LiveView"
    title = context.get("title") or default_title
    render_title = (title + suffix) if title is not None else "LiveView"
    main_content = contentWrapper(
        context,
        Markup(
            f"""
      <div
        data-phx-main="true"
        data-phx-session="{context["session"]}"
        data-phx-static=""
        id="phx-{context["id"]}"
        >
        {context["content"]}
    </div>"""
        ),
    )

    additional_head_elements = "\n".join(context["additional_head_elements"])

    return (
        Markup(
            f"""
<!DOCTYPE html>
<html lang="en">
    <head>
      <title data-suffix="{suffix}">{render_title}</title>
      <meta name="csrf-token" content="{context["csrf_token"]}" />
      <meta charset="utf-8">
      <meta http-equiv="X-UA-Compatible" content="IE=edge">
      <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
      {css}
      <script defer type="text/javascript" src="/static/assets/app.js"></script>
      {additional_head_elements}
    </head>
    <body>"""
        )
        + main_content
        + Markup(
            """
    </body>
</html>
"""
        )
    )
