from . import utils
from . import errors
from .tree import PartsTree
from .nodes import Node, NodeVisitor, register, Expression

from .components.component_factory import get_component_factory


# live_component nodes


#
#     {% live_component <expr> %}
#
#     {% live_component <expr> with <name> = <expr> %}
#
#     {% live_component <expr> with <name1> = <expr> & <name2> = <expr> %}
#
# Requires a Live Component name which can be supplied as either a string literal or a variable
# resolving to a string. This name will be passed to the registered component factory.
@register("live_component")
class LiveComponentNode(Node):
    def process_token(self, token):
        self.variables = {}
        parts = utils.splitre(token.text[14:], ["with"])

        if len(parts) == 1:
            self.template_arg = parts[0]
            self.template_expr = Expression(parts[0], token)
        elif len(parts) == 2:
            self.template_arg = parts[0]
            self.template_expr = Expression(parts[0], token)
            chunks = utils.splitc(parts[1], "&", strip=True, discard_empty=True)
            for chunk in chunks:
                try:
                    name, expr = chunk.split("=", 1)
                    self.variables[name.strip()] = Expression(expr.strip(), token)
                except:
                    raise errors.TemplateSyntaxError(
                        "Malformed 'include' tag.", token
                    ) from None
        else:
            raise errors.TemplateSyntaxError("Malformed 'include' tag.", token)

    def visit_node(self, context, visitor):
        template_name = self.template_expr.eval(context)
        if isinstance(template_name, str):
            ######### TODO: We need to load the component...
            # Maybe we can require it to be fully qualified for now and figure out a way to alias it later...
            # maybe something similar to ibis loader for components...
            # maybe like @component("ShortName")...
            # not sure if that would work for sharing components between projects...?... maybe it would...

            factory = get_component_factory()
            if factory:
                template_vars = {}
                for name, expr in self.variables.items():
                    context[name] = expr.eval(context)
                    template_vars[name] = context[name]

                id = context.get("id", None)
                if not id:
                    msg = f"No 'id' variable found in the context. "
                    msg += f"The 'id' variable is required by the 'include' tag in "
                    msg += f"template '{self.token.template_id}', line {self.token.line_number}."
                    raise errors.TemplateRenderingError(msg, self.token)
                component = factory.register_component(id, template_name, template_vars)

                context.push()

                visitor(component)
                context.pop()
            else:
                msg = f"No template loader has been specified. "
                msg += f"A template loader is required by the 'include' tag in "
                msg += f"template '{self.token.template_id}', line {self.token.line_number}."
                raise errors.TemplateLoadError(msg)
        else:
            msg = f"Invalid argument for the 'include' tag. "
            msg += f"The variable '{self.template_arg}' should evaluate to a string. "
            msg += f"This variable has the value: {repr(template_name)}."
            raise errors.TemplateRenderingError(msg, self.token)

    def wrender(self, context):
        output = []

        def visitor(ref):
            pass

        self.visit_node(context, visitor)

        return "".join(output)

    def tree_parts(self, context) -> PartsTree:
        output = []

        def visitor(ref):
            output.append(ref.cid)

        self.visit_node(context, visitor)
        return output[0] if output else PartsTree()
