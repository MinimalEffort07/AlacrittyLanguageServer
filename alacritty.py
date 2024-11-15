from pygls.lsp.server import LanguageServer
from pygls.workspace.text_document import TextDocument
from lsprotocol import types
from configuration import config
import logging

FORMAT = "[%(filename)s:%(lineno)s - %(funcName)20s() ] %(message)s"
logging.basicConfig(filename="pygls.log", filemode="w", level=logging.DEBUG, format=FORMAT)

log = logging.getLogger(__name__)

server = LanguageServer("Alacritty-LanguageServer", "v0.1")

def get_toml_section(params: types.CompletionParams, document: TextDocument) -> str:
    """
    Gets the first TOML section definition encoutered, beginning from the current line and
    searching upwards.

    Args:
        params: Type completion parameters from pygls used to get the current line number
        document: Text document object which contains a list of each line in the document being
        edited.
    Returns:
        A string representing the TOML section value without the enclosing square brackes, or an
        empty string on failure.
    """
    line = params.position.line

    while line >= 0 and document.lines[line][0] != "[":
        log.debug(f"Not the section line: {line}: {document.lines[line]}")
        line -= 1

    if line < 0:
        log.debug(
            "Reached beginning of file looking for section line but couldn't find it"
        )
        return ""

    # Do two strips, the first targeting whitespace and the second to target the toml square
    # brackets. Could do it in one but don't want to have to deal with all the different whitespace
    # characters that could be at the end of the line e.g. ^M on windows.
    section = document.lines[line].strip().strip("[]")
    log.debug(f"Section line: {section} , on line number: {line}")

    return section

def get_nested_dict_value(dictionary: dict, keys: str):
    """
    Indexes into a nested dictionary 'dictionary', using a period separated string of key values.

    E.g.

    Dict: { "Level1": { "Level2": { "Level3": "Value3" } } }

    Keys = "Level1", returns { "Level2": { "Level3": "Value3" } }
    Keys = "Level1.Level2", returns { "Level3": "Value3" }
    Keys = "Level1.Level2.Level3", returns "Value3"

    If keys contain a value that doesn't exist, return back the level above what was trying to be
    indexed into.

    e.g.

    Keys = "Level1.Level6", returns { "Level2": { "Level3": "Value3" } }

    Essentially the keys string is truncated at the first instance of a bad value.

    Args:
        dictionary: Dictionary to index into
        keys: Period seperated string of nested key values
    Returns:
        A value from the dictionary parameter
    """
    if not keys:
        return dictionary

    key_components = keys.split(".")
    log.debug(f"components: {key_components}")

    key_depth = len(key_components)
    log.debug(f"depth: {key_depth}")

    level = 0
    sub_section = dictionary

    while level < key_depth:
        log.debug(f"level: {level}, key_components: {key_components}, sub_section: {sub_section}")
        if key_components[level] not in sub_section:
            return sub_section
        else:
            sub_section = sub_section[key_components[level]]
            log.debug(f"sub_section: {sub_section}")
            level += 1

    return sub_section


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=["="])
)
def completions(params: types.CompletionParams) -> list:
    """
    Provides completion options for the current cursor position in the alacritty TOML configuration
    file.

    Handles completion:
        1. In a section definition e.g. [gene<autocomplete reqeusted>
        2. On an empty line within a section: e.g.
            [general]
            <autocomplete requested>
        3. On a partially completed key within a section e.g.
            [general]
            wor<autocomplete requested>
        4. On a completed key within a section e.g.
            [general]
            working_directory<autocomplete requested>
        5. On a completed key within a section after the equal sign e.g.
            [general]
            working_directory = <autocomplete requested>
        6. On partially completed values within a section after the equal sign
            [window]
            dynamic_title = fal<autocomplete requested>
        7. On an empty line before the first section e.g.
            <start of file>
            [<autocomplete requested>
    Unhandled secnarios:
        1. Line is "illegitimate_key = <autocomplete requested>"
        2. Line is "illegitimate_unfinished_key<autocomplete requested>"
        * Both of these cases if a job for diagnostics and/or code_action*
    Args:
        params: Type completion parameters from pygls used to get the current line number
    Returns:
        A list of strings that will be provided as the completion options

    """
    document = server.workspace.get_text_document(params.text_document.uri)

    current_line = document.lines[params.position.line].strip()

    try:
        # Get section (or partial section) as period delimited values
        current_section = get_toml_section(params, document)
        section_value_space = get_nested_dict_value(config, current_section)
        completion_options = None

        if current_line and current_line[0] == "[":
            # We are completing a section line
            completion_options = section_value_space
        else:
            # We are completing an entry line
            key = current_line.split("=")[0].strip()
            value = None
            if len(current_line.split("=")) == 2:
                value = current_line.split("=")[1].strip()

            if value or (key in section_value_space):
                completion_options = section_value_space[key]
            else:
                completion_options = section_value_space

        return [types.CompletionItem(label=opt) for opt in completion_options if None != opt]

    except KeyError as e:
        log.error(e)
        return []
    except IndexError as e:
        log.error(e)
        return []

if __name__ == "__main__":
    server.start_io()
