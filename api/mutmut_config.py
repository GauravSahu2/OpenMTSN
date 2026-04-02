# mutmut configuration for OpenMTSN routing engine mutation testing.
# Run: cd api && mutmut run


def init():
    """Mutmut configuration callback."""
    pass


def pre_mutation(context):
    """
    Skip mutations in non-critical code (logging, docstrings).
    Focus mutation testing on the routing engine logic.
    """
    # Only mutate the routing engine module
    if "routing_engine" not in context.filename:
        context.skip = True
