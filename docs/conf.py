import datetime
from sphinx_rtd_theme import get_html_theme_path

# -- General configuration -----------------------------------------------------

general_theme = "sphinx_rtd_theme"

# Documentation theme.
theme_path = get_html_theme_path() + "/" + general_theme

# Minimal Sphinx version.
needs_sphinx = "5.1.0"

# Add any extenstions here. These could be both Sphinx or custom ones.
extensions = [
    "myst_parser",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.ifconfig",
    "sphinx.ext.extlinks",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinxcontrib.mermaid",
    "numpydoc",
]

# If true, figures, tables and code-blocks are automatically numbered
# if they have a caption.
numfig = True

# The suffix of source filenames.
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

# The main toctree document.
master_doc = "index"

# General information about the project.
project = "Coreblocks documentation"
output_filename = "coreblocks-docs"
authors = "Kuźnia Rdzeni"
copyright = authors + ", {}".format(datetime.datetime.now().year)

# Specify time format. Used in 'Last Updated On:'.
today_fmt = "%H:%M %Y-%m-%d"

# The name of the Pygments (syntax highlighting) style to use.
# This affects the code blocks. More styles: https://pygments.org/styles/
pygments_style = "sphinx"

# -- HTML output ---------------------------------------------------------------

# The theme to be used for HTML documentation.
html_theme = general_theme

# The title to be shown at all html documents.
# Deafult is "<project> v<release> documentation".
html_title = project

# A shorter title to appear at the navigation bar. Default is html_title.
html_short_title = "Coreblocks"

# 'Last updated on:' timestamp is inserted at every page bottom,
# using the given strftime format. To disable set it to ''.
html_last_updated_fmt = today_fmt

# If True show "Created using Sphinx" in the HTML footer.
html_show_sphinx = False

# Logo of this project.
html_logo = "images/logo-banner.svg"

# -- Custom filters ------------------------------------------------------------


# Exclude some methods from the api documentation
def hide_non_private(app, what, name, obj, skip, options):
    if "elaborate" in name:
        # skip elaborates
        return True
    elif "__init__" == name:
        # Include __init__ (excluded by default)
        return False
    else:
        # otherwise generate an entry
        return None


def setup(app):
    app.connect("autodoc-skip-member", hide_non_private)


# If set to False it doesn't generate summary of class Methods if not
# explicitly described in docsting. This prevents many mostly empty Method
# sections in most classes since 'elaborate' methods are not documented.
numpydoc_show_class_members = False

# Show typehints in the signature
autodoc_typehints = "signature"

# Display the class signature as a method
autodoc_class_signature = "separated"

# Auto generate anchors for # - ### headers
myst_heading_anchors = 3

# Compatibility with Amaranth docstrings
rst_prolog = """
.. role:: py(code)
   :language: python
"""

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "amaranth": ("https://amaranth-lang.org/docs/amaranth/latest/", None),
}
