# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-06-03

### Added

- GRPC calls to hide and show streams
- GRPC call to remove a stream from the stream proxy

### Removed

- API calls to the stream proxy to interact with streams (adding and removing streams has to go through grpc control server)

### Changed

- Control server communicates with stream proxy through reserved channel

## [0.2.1] - 2026-05-04

### Changed

- Frame dropping mechanism is specific for each client connection
- Connection loss to camera stream will be retried up to 3 times
- Improved signal handling
- Logging colors changed

## [0.2.0] - 2025-02-12

### Added

- Customized loggers for different parts of the application

### Changed

- update version of video-streamer to increase number of supported camera streams

## [0.1.0] - 2025-01-06

### Added

- Proxy for web streams
- GRPC server for process control
- Processes for Recording, Saving and Flow Control
