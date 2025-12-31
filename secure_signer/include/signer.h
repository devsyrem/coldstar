/**
 * Solana Secure Signer - C Header for FFI
 * 
 * This header defines the C-compatible interface for the Rust signing library.
 * 
 * Memory Management:
 * - All strings returned by signer_* functions are allocated by Rust
 * - Use signer_free_result() to free SignerResult structs
 * - The version string from signer_version() is static and should NOT be freed
 * 
 * Thread Safety:
 * - All functions are thread-safe
 * 
 * Security:
 * - Private keys are kept in mlock'd memory
 * - All sensitive data is zeroized after use
 * - Passphrases are processed in secure memory
 */

#ifndef SOLANA_SECURE_SIGNER_H
#define SOLANA_SECURE_SIGNER_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * Result structure for signing operations.
 * 
 * On success (error_code == 0):
 *   result contains a JSON string with the operation result
 * 
 * On failure (error_code != 0):
 *   result contains an error message
 * 
 * Error codes:
 *   0 - Success
 *   1 - Null pointer argument
 *   2 - Invalid UTF-8
 *   3 - Base58/Base64 decode error
 *   4 - Crypto operation failed
 *   5 - Serialization error
 */
typedef struct {
    int32_t error_code;
    char* result;
} SignerResult;

/**
 * Create an encrypted key container from a private key.
 * 
 * @param private_key_b58 Base58-encoded private key (32 or 64 bytes)
 * @param passphrase      Null-terminated passphrase for encryption
 * @return SignerResult with JSON container on success
 * 
 * The returned JSON has the format:
 * {
 *   "version": 1,
 *   "salt": "<base64>",
 *   "nonce": "<base64>",
 *   "ciphertext": "<base64>",
 *   "public_key": "<base58>"
 * }
 */
SignerResult signer_create_container(
    const char* private_key_b58,
    const char* passphrase
);

/**
 * Sign a transaction using an encrypted key container.
 * 
 * @param container_json  JSON string of the encrypted container
 * @param passphrase      Null-terminated passphrase for decryption
 * @param transaction_b64 Base64-encoded unsigned transaction bytes
 * @return SignerResult with signing result on success
 * 
 * The returned JSON has the format:
 * {
 *   "signature": "<base58>",
 *   "signed_transaction": "<base64>",
 *   "public_key": "<base58>"
 * }
 */
SignerResult signer_sign_transaction(
    const char* container_json,
    const char* passphrase,
    const char* transaction_b64
);

/**
 * Sign a message directly with a private key.
 * 
 * WARNING: This is less secure than using an encrypted container.
 * The private key is still processed in secure memory, but it must
 * be passed as a parameter.
 * 
 * @param private_key_b58 Base58-encoded private key
 * @param message_b64     Base64-encoded message to sign
 * @return SignerResult with signing result on success
 */
SignerResult signer_sign_direct(
    const char* private_key_b58,
    const char* message_b64
);

/**
 * Free a SignerResult structure.
 * 
 * This must be called for every SignerResult returned by the library
 * to prevent memory leaks.
 * 
 * @param result The result to free
 */
void signer_free_result(SignerResult result);

/**
 * Free a string allocated by the library.
 * 
 * @param ptr Pointer to string (may be NULL)
 */
void signer_free_string(char* ptr);

/**
 * Get the library version.
 * 
 * @return Static version string - do NOT free this
 */
const char* signer_version(void);

/**
 * Check if memory locking (mlock) is supported.
 * 
 * @return 1 if supported, 0 otherwise
 */
int32_t signer_check_mlock_support(void);

#ifdef __cplusplus
}
#endif

#endif /* SOLANA_SECURE_SIGNER_H */
