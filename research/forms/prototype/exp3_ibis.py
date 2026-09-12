"""Experiment 3: can pyview's vendored Ibis engine express field-accessor syntax like
{{ form.name.value }}, {{ form.addresses.0.city | input }}, {% for row in form.addresses %} ... ?"""
import sys; sys.path.insert(0, __import__("os").path.dirname(__file__))
from markupsafe import Markup
from pydantic import BaseModel, Field
from pyview.vendor.ibis import Template, filters
from pyview_forms_proto import Form

class Address(BaseModel):
    city: str = Field(min_length=2, title="City")
class Profile(BaseModel):
    name: str = Field(min_length=3)
    addresses: list[Address] = []

@filters.register
def input(field, **kw):
    attrs = {"type": field.input_type, "name": field.name, "id": field.id, "value": field.value, **field.constraints, **kw}
    s = " ".join(f'{k}="{v}"' if v is not True else k for k, v in attrs.items() if v is not False and v != "")
    return Markup(f"<input {s}>")

@filters.register
def errors(field):
    return Markup("".join(f'<p class="error">{e}</p>' for e in field.errors))

form = Form.for_model(Profile, as_="profile")
form.submit([("profile[name]", "ab"), ("profile[addresses][0][city]", "P"), ("profile[addresses][1][city]", "Rome")])

tpl = Template("""
<label for="{{ form.name.id }}">{{ form.name.label }}</label>
{{ form.name | input }}
{{ form.name | errors }}
{% for row in form.addresses %}
  <div>{{ row.city | input }} {{ row.city | errors }}</div>
{% endfor %}
direct index: {{ form.addresses.1.city.value }}
""")
print(tpl.render({"form": form}))
