# Security And Privacy

ElectionLab stores optional provider credentials with the operating system credential service through `keyring`. API keys should not be written to this repository, issue comments, screenshots, logs or release archives.

Do not commit:

- `portable_config.json`
- `ElectionLabData/`
- Knowledge Vault databases or portraits
- campaign saves and simulation archives
- logs, crash reports and research caches
- local model files
- virtual environments and installer caches
- `.env` files or other secret material

If you accidentally commit private data, rotate any exposed credentials first, then remove the data from Git history before publishing or merging.
