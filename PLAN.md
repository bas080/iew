# How to implement lsp in python

from lsprotocol import types
from pygls.server import LanguageServer

server = LanguageServer("my-language-server", "v0.1")


@server.feature(types.TEXT_DOCUMENT_COMPLETION)
def completions(params: types.CompletionParams) -> types.CompletionList:
  return types.CompletionList(
      is_incomplete=False,
      items=[types.CompletionItem(label="hello")],
  )


if __name__ == "__main__":
  server.start_io()
