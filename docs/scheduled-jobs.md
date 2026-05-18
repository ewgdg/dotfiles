# Scheduled Jobs

Prefer systemd timers over cron jobs when this repo manages scheduled system work.

## Policy

- Use one scheduler for a job, not both cron and systemd.
- Prefer systemd timers for managed services because they are explicit, inspectable, and easy to enable/disable idempotently.
- Disable or block packaged cron jobs when equivalent systemd timers are managed elsewhere.
- Document exceptions near the package that needs cron.

## Duplicate Job Risk

Some packages ship cron jobs while also providing systemd timers. Do not leave both active unless duplicate execution is intentional.

Duplicate scheduled jobs can cause:

- repeated snapshots/backups
- duplicate cleanup runs
- confusing logs
- extra disk or CPU use
- policy drift after package upgrades

## Pacman `NoExtract` Pattern

On Arch, if a package keeps reinstalling unwanted cron files, block those files in `pacman.conf` with `NoExtract` and explain why with a nearby comment.

Example:

```conf
# Package is managed through systemd timers elsewhere.
# Do not extract packaged cron jobs, or scheduled work can run twice.
NoExtract = /etc/cron.daily/example /etc/cron.hourly/example
```

Before removing a `NoExtract` rule, check for managed systemd timers for the same job and disable one scheduler first.
