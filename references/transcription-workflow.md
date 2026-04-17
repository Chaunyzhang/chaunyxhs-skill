# Transcription Workflow

## Goal

Turn a local file or a public audio URL into:

- transcription text
- segment data when available
- normalized metadata about the source and model

## Preferred backend split

Use DashScope with two official paths:

- `Transcription` + `paraformer-v2` for public audio URLs
- `Recognition` + `paraformer-realtime-v2` for local audio files

## Source handling rules

1. Local audio file:
   - send directly through the local-file recognition path
2. Public audio URL:
   - send directly through file transcription
3. Local video file:
   - extract audio locally first
   - then send the extracted audio file through the local-file recognition path

## Why extract audio from video first

That path is more predictable than relying on undocumented or loosely documented video-file behavior in the ASR layer.

## Storage note

This workflow avoids manually uploading files to OSS first.
It still sends the audio content to DashScope for inference, so it should not be treated as a zero-server-exposure path.
