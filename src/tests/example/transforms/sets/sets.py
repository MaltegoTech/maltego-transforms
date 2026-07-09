from maltego.server import TransformSet, register_transform_set

TEST_RUN = False


__all__ = [
    "FooSet",
]


@register_transform_set
class FooSet(TransformSet):
    description = "maltego-transforms test set"
    transforms = [
        "onprem.com.maltego.pyjinx.transform",
        "onprem.com.maltego.pyjinx.transform_pong"
    ]
