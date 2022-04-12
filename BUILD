load("@com_github_grpc_grpc//bazel:python_rules.bzl", "py_proto_library")
load("@rules_proto//proto:defs.bzl", "proto_library")
load("@subpar//:subpar.bzl", "par_binary")

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

par_binary(
    name = "loop_archive",
    srcs = ["loop_archive.py"],
    python_version = "PY3",
    deps = [
        ":loop_archive_py_proto",
        "@abseil//absl:app",
        "@abseil//absl/flags",
        "@abseil//absl/logging",
    ],
)

py_test(
    name = "loop_archive_test",
    srcs = ["loop_archive_test.py"],
    python_version = "PY3",
    deps = [
        ":loop_archive",
        ":loop_archive_py_proto",
        "@abseil//absl/testing:absltest",
        "@abseil//absl/testing:flagsaver",
        "@abseil//absl/testing:parameterized",
        "@rules_python//python/runfiles",
    ],
)
