# macOS Build and Code Signing Resources

This directory contains resources for building and code signing the AceForge macOS application.

## Files

### entitlements.plist
Defines the security entitlements for the macOS application. This file specifies what permissions and capabilities the app needs:

- **Network access**: For the Flask web server
- **File system access**: For reading/writing audio files and ML models
- **JIT compilation**: Required for PyTorch and ML frameworks
- **Unsigned executable memory**: Allows Python and native extensions to run
- **Library validation disabled**: Allows loading third-party frameworks and libraries

### codesign.sh
Automated code signing script that signs the `.app` bundle to prevent macOS security warnings.

## Usage

### Automated (GitHub Actions)
The build workflow automatically runs code signing after PyInstaller creates the app bundle:

```yaml
- name: Code sign the app bundle
  run: |
    chmod +x build/macos/codesign.sh
    ./build/macos/codesign.sh dist/AceForge.app
  env:
    MACOS_SIGNING_IDENTITY: ${{ secrets.MACOS_SIGNING_IDENTITY || '-' }}
```

### Manual Local Builds
After building with PyInstaller, run the code signing script:

```bash
# Ad-hoc signing (no certificate required)
./build/macos/codesign.sh dist/AceForge.app

# Or with a specific signing identity
MACOS_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAM123)" \
  ./build/macos/codesign.sh dist/AceForge.app
```

## Code Signing Modes

### 1. Ad-hoc Signing (Development)
**Default behavior** - Uses the special identifier "-" which creates an ad-hoc signature:
- No Apple Developer certificate required
- App will run without the `sudo xattr -cr` workaround
- App is signed but not notarized
- Suitable for local development and testing
- Will still show a security warning on first launch (user must right-click > Open)

```bash
# Explicit ad-hoc signing
MACOS_SIGNING_IDENTITY="-" ./build/macos/codesign.sh dist/AceForge.app
```

### 2. Developer ID Signing (Distribution)
For distributing to users outside the Mac App Store:
- Requires Apple Developer Program membership ($99/year)
- Uses "Developer ID Application" certificate
- Can be notarized by Apple for gatekeeper approval
- Users can double-click to open (no security warnings)

```bash
# Sign with Developer ID
MACOS_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAM123)" \
  ./build/macos/codesign.sh dist/AceForge.app
```

### 3. Notarization (Full Distribution)
For the smoothest user experience:
1. Sign with Developer ID certificate
2. Submit to Apple for notarization
3. Staple the notarization ticket to the app

```bash
# After code signing with Developer ID:
# Replace "YourNotaryProfile" with your keychain profile name
# (Created via: xcrun notarytool store-credentials)
xcrun notarytool submit AceForge-macOS.dmg \
  --keychain-profile "YourNotaryProfile" \
  --wait

xcrun stapler staple dist/AceForge.app
```

## Setting Up Certificates

### For GitHub Actions
1. Export your Developer ID certificate from Keychain Access
2. Create a base64-encoded string: `base64 -i certificate.p12`
3. Add GitHub secrets:
   - `MACOS_CERTIFICATE`: Base64-encoded certificate
   - `MACOS_CERTIFICATE_PWD`: Certificate password
   - `MACOS_SIGNING_IDENTITY`: Certificate identity (e.g., "Developer ID Application: Your Name (TEAM123)")

### Finding Your Signing Identity
```bash
# List all code signing identities
security find-identity -v -p codesigning

# Common identity formats:
# - "Developer ID Application: Company Name (TEAM123)" 
#     → For distribution outside the App Store (public release)
# - "Apple Development: Your Name (TEAM123)" 
#     → For Xcode development and testing on registered devices
# - "-" 
#     → Ad-hoc signing (no certificate, works locally but shows security warning)
```

## Troubleshooting

### "The app is damaged and can't be opened"
This happens when the app is unsigned or the signature is invalid. Solutions:
1. Run the code signing script: `./build/macos/codesign.sh dist/AceForge.app`
2. Or manually remove quarantine attribute: `sudo xattr -cr dist/AceForge.app`

### "Code signing failed"
- Check if the entitlements.plist exists
- Verify your signing identity is correct
- For Developer ID signing, ensure the certificate is valid and not expired

### "Failed to sign *.dylib or *.so files"
This is usually non-critical - the script continues and signs the main bundle. These failures typically occur for:
- System libraries that are already signed
- Stub files that don't need signing

### Verification
Check the signature of your app:
```bash
# Verify signature
codesign --verify --deep --strict --verbose=2 dist/AceForge.app

# Display signature details
codesign -dv --verbose=4 dist/AceForge.app

# Check entitlements
codesign -d --entitlements - dist/AceForge.app
```

## References

- [Apple Code Signing Guide](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)
- [Entitlements Documentation](https://developer.apple.com/documentation/bundleresources/entitlements)
- [Original inspiration](https://github.com/dylanwh/lilguy/blob/main/macos/build.sh)

## License

These build resources are part of the AceForge project and follow the same license terms.
