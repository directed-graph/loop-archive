load("@com_github_grpc_grpc//bazel:python_rules.bzl", "py_proto_library")
load("@rules_proto//proto:defs.bzl", "proto_library")

proto_library(
    name = "loop_archive_proto",
    srcs = ["loop_archive.proto"],
    deps = [
        "@com_google_protobuf//:any_proto",
        "@com_google_protobuf//:descriptor_proto",
    ],
)

py_proto_library(
    name = "loop_archive_py_proto",
    deps = [
        ":loop_archive_proto",
    ],
)
