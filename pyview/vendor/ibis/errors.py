# Base class for all exception types raised by the template engine.
class TemplateError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        if hasattr(self, "token") and self.token is not None:
            return f"Template '{self.token.template_id}', line {self.token.line_number}: {self.msg}"
        return self.msg


# This exception type may be raised while attempting to load a template file.
class TemplateLoadError(TemplateError):
    pass


# This exception type is raised if the lexer cannot tokenize a template string.
class TemplateLexingError(TemplateError):

    def __init__(self, msg, template_id, line_number):
        super().__init__(msg)
        self.template_id = template_id
        self.line_number = line_number

    def __str__(self):
        return f"Template '{self.template_id}', line {self.line_number}: {self.msg}"


# This exception type may be raised while a template is being compiled.
class TemplateSyntaxError(TemplateError):

    def __init__(self, msg, token):
        super().__init__(msg)
        self.token = token


# This exception type may be raised while a template is being rendered.
class TemplateRenderingError(TemplateError):

    def __init__(self, msg, token):
        super().__init__(msg)
        self.token = token


# This exception type is raised in strict mode if a variable cannot be resolved.
class UndefinedVariable(TemplateError):

    def __init__(self, msg, token):
        super().__init__(msg)
        self.token = token

