from unittest.mock import Mock

from dissect.cstruct.parser import TokenParser


def test_preserve_comment_newlines():
    cdef = """
    // normal comment
    #define normal_anchor
    /*
     * Multi
     * line
     * comment
     */
    #define multi_anchor
    """
    data = TokenParser._remove_comments(cdef)

    mock_token = Mock()
    mock_token.match.string = data
    mock_token.match.start.return_value = data.index("#define normal_anchor")
    assert TokenParser._lineno(mock_token) == 3

    mock_token.match.start.return_value = data.index("#define multi_anchor")
    assert TokenParser._lineno(mock_token) == 9
