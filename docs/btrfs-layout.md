# Btrfs Layout

One GPT disk, no LUKS, no LVM, no RAID:

| Partition | Size | Type | Mount |
| --- | --- | --- | --- |
| `p1` | 1 GiB | EFI System, vfat | `/boot` |
| `p2` | remainder | btrfs, Linux x86-64 root GPT type | everything else |

No swap partition.

## Subvolumes

| Subvolume | Mount | Purpose |
| --- | --- | --- |
| `@` | `/` | system root |
| `@home` | `/home` | user data |
| `@log` | `/var/log` | kept out of root snapshots |
| `@pkg` | `/var/cache/pacman/pkg` | kept out of root snapshots |
| `@.snapshots` | `/.snapshots` | snapper `root` snapshot directory |
| `@home/.snapshots` | not mounted | snapper `home` snapshot directory |

The first five are direct children of the filesystem top level.
`@home/.snapshots` is nested inside `@home`, and snapshots do not recurse into
nested subvolumes.

## Mounts

One fstab line per subvolume:

```
UUID=<uuid>  <mountpoint>  btrfs  defaults,noatime,compress=zstd:-3,ssd,discard=async,subvol=/<subvolume>  0 0
```

- `compress=zstd:-3` is a zstd fast mode: cheaper writes, lower ratio, chosen for
  fast SSD storage. It needs Linux 6.15 or newer; older kernels fail the mount,
  so use `compress=zstd` there.
- Compression applies per filesystem, so all lines should carry the same value.
- `ssd` and `discard=async` are current kernel defaults and can be omitted.

## Creating It

```sh
DISK=/dev/nvme0n1   # adjust

sgdisk --clear \
  --new=1:0:+1GiB --typecode=1:ef00 --change-name=1:EFI \
  --new=2:0:0     --typecode=2:4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709 --change-name=2:root \
  "$DISK"
mkfs.fat -F 32 -n EFI "${DISK}p1"
mkfs.btrfs -L root "${DISK}p2"

mount "${DISK}p2" /mnt
btrfs subvolume create /mnt/@{,@home,@log,@pkg,@.snapshots}
umount /mnt

opts=noatime,compress=zstd:-3
mount -o "$opts",subvol=/@ "${DISK}p2" /mnt
mkdir -p /mnt/{boot,home,.snapshots,var/log,var/cache/pacman/pkg}
mount -o "$opts",subvol=/@home       "${DISK}p2" /mnt/home
mount -o "$opts",subvol=/@log        "${DISK}p2" /mnt/var/log
mount -o "$opts",subvol=/@pkg        "${DISK}p2" /mnt/var/cache/pacman/pkg
mount -o "$opts",subvol=/@.snapshots "${DISK}p2" /mnt/.snapshots
mount "${DISK}p1" /mnt/boot

pacstrap -K /mnt base linux linux-firmware
genfstab -U /mnt >> /mnt/etc/fstab
```

Then follow the installation guide for locale, users and bootloader, and run
`./init.sh` and `dotman push` in this repo to install the snapper configs and
enable the timers.

Check it:

```sh
findmnt -t btrfs -o TARGET,SOURCE
sudo btrfs subvolume list /
```

## Not Included

- Bootloader, swap, additional filesystems, UUIDs and labels: machine-local,
  never copied between machines.
- `var/lib/{portables,machines}`: created by systemd.

