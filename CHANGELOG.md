# Changelog

All notable changes to `barber-saas-worker` are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-10-08

MVP 2 (corte 2): first release of this repository to `main`, promoted from `develop` through `qa`
with `git cherry-pick -x` (norm 10–11).

User stories: code-corhuila/barber-saas-docs#4, code-corhuila/barber-saas-docs#5, code-corhuila/barber-saas-docs#9, code-corhuila/barber-saas-docs#59.

### Added

- **domain:** the event, its routing and the retry policy
- **relay:** relay each outbox and run the daily jobs
- **adapters:** urllib clients, the scheduler and the health probe
- **app:** wire the jobs from the environment and ship the image
- **deploy:** deliver events to notifications-api
- **deploy:** relay the identity-auth outbox
- **relay:** relay loyalty's outbox before loyalty consumes events
- **deploy:** deliver events to loyalty-api
- **routing:** deliver AppointmentCreated to loyalty

### Fixed

- **jobs:** wait before calling a service that did not answer

### Documentation

- **readme:** point the header to Barber Saas and barber-saas-docs
- **readme:** explain the worker, its delivery rules and how to run it
- **routing:** link the coupon route to its decision record

### Maintenance

- set up the Python package, the layer contracts and CI

[2.0.0]: https://github.com/code-corhuila/barber-saas-worker/releases/tag/v2.0.0
