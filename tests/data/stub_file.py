from dissect.cstruct import cstruct

c_def = """
struct Test {
  uint32  a;
  uint32  b;
}
"""

c_structure = cstruct().load(c_def)
