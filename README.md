
Loop Archive is a program that archives from one or more source locations to a
single destination. Archiving is done by moving items from the source to the
specified destination.  While doing so, if the specified destination requires
more storage than the allocated amount, the program will delete some of the
existing items, starting from the oldest item.


## Building

If you just want to build the binary to run, you can do so with either Docker
or [Bazel](https://bazel.build). It is easiest with Bazel:

```bash
bazel build :loop_archive.par
```

Then, `bazel-bin/loop_archive.par` will be the binary.

If you want to use Docker, see [Installing](#installing).


## Installing

We have an AUR package for installation:

```bash
git clone https://aur.archlinux.org/loop-archive-git.git
cd loop-archive-git

# If running rootful Docker.
./docker_build.bash

# If running rootless Docker.
ROOTLESS=yes ./docker_build.bash

# For Archlinux.
sudo pacman -U loop-archive-git-...pkg.tar.zst

# For other distributions or just to get the binary.
tar -xf loop-archive-git-...pkg.tar.zst
```


## Configuring and Running

Simply write your `everchanging.loop_archive.Config` proto configuration and
run with with that file passed to the `--config_file` flag.

Alternatively, we include a `systemd` template [installed](#installing) as part
of the AUR package. Once you have the configuration file, you can run directly
with `systemd` as follows:

```
systemctl --user start loop-archive@$(systemd-escape ${config_path}).service
```

Where `${config_path}` is the config file with
`everchanging.loop_archive.Config` proto.


## Automation

You can automate running of Loop Archive by using the [installed](#installing)
timer unit:

```
systemctl --user enable --now loop-archive@$(systemd-escape ${config_path}).timer
```

Where `${config_path}` is the `everchanging.loop_archive.Config` proto
configuration.
