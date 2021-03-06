Elixir
======

Elixir is a declarative layer on top of the [SQLAlchemy library]
(http://www.sqlalchemy.org/). It is a fairly thin wrapper, which provides
the ability to create simple Python classes that map directly to relational
database tables (this pattern is often referred to as the Active Record design
pattern), providing many of the benefits of traditional databases
without losing the convenience of Python objects.

Elixir is intended to replace the ActiveMapper SQLAlchemy extension, and the
TurboEntity project but does not intend to replace SQLAlchemy's core features,
and instead focuses on providing a simpler syntax for defining model objects
when you do not need the full expressiveness of SQLAlchemy's manual mapper
definitions.

