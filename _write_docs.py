import pathlib
content = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
pathlib.Path(sys.argv[2]).write_text(content, encoding='utf-8')
print(f'{sys.argv[2]} created')
