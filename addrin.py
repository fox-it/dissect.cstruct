from dissect.cstruct import cstruct, dumpstruct

if __name__ == '__main__':
    definitions = 'structs.h'
    contents = ''
    with open(definitions, "r") as file:
        contents = file.read()

    structs = cstruct()
    structs.load(contents)
