def verify_compiled(struct, compiled):
    return ("+compiled" in repr(struct)) == compiled
