from .draft07 import CodeGeneratorDraft07


class CodeGeneratorDraft2019(CodeGeneratorDraft07):
    FORMAT_REGEXS = dict(CodeGeneratorDraft07.FORMAT_REGEXS, **{
        'uuid': r'^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\Z',
        # ISO 8601 duration from RFC 3339 Appendix A
        'duration': (
            r'^P(?!$)'
            r'(?:'
            r'[0-9]+W'
            r'|(?:[0-9]+Y)?(?:[0-9]+M)?(?:[0-9]+D)?(?:T(?=[0-9])(?:[0-9]+H)?(?:[0-9]+M)?(?:[0-9]+S)?)?'
            r')\Z'
        ),
    })
