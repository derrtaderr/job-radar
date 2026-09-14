MINIMAL_TYP = '#set page(paper: "us-letter")\n= Hello\nA one-page test document.\n'

# Missing colon after `paper` — must fail to compile.
BROKEN_TYP = '#set page(paper "us-letter")\n'
