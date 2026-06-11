#!/usr/bin/env python3
"""
Wrapper for psycopg2 to work around encoding issues with Latin-1 PostgreSQL clusters
"""
import psycopg2.extensions
import psycopg2 as _psycopg2
import codecs

# Monkey-patch the original connect function
_original_connect = _psycopg2.connect

def _connect_with_encoding_fallback(*args, **kwargs):
    """Wrapper for psycopg2.connect that handles encoding errors"""
    try:
        return _original_connect(*args, **kwargs)
    except UnicodeDecodeError as e:
        # Try alternative encodings
        print(f"⚠️  UnicodeDecodeError: {e}. Retrying with different encoding...")
        
        # Try LATIN1 encoding instead of UTF-8
        if 'client_encoding' not in kwargs:
            kwargs['client_encoding'] = 'LATIN1'
        
        try:
            return _original_connect(*args, **kwargs)
        except:
            # If still fails, try with no encoding parameter
            kwargs.pop('client_encoding', None)
            return _original_connect(*args, **kwargs)

# Replace the original function
_psycopg2.connect = _connect_with_encoding_fallback

# Also try to patch libpq environment variables
import os
os.environ['PGCLIENTENCODING'] = 'LATIN1'
os.environ['PGLOCALE'] = 'C'

def get_connection_safe(dsn_or_dict, **kwargs):
    """Safe connection wrapper"""
    try:
        # First try with default parameters
        conn = _psycopg2.connect(dsn_or_dict, **kwargs)
        return conn
    except UnicodeDecodeError as e:
        print(f"⚠️  Encoding error during connection: {e}")
        # Force LATIN1 and retry
        if isinstance(dsn_or_dict, str):
            # Parse the DSN-style string and try with LATIN1
            try:
                conn = _psycopg2.connect(dsn_or_dict, client_encoding='LATIN1')
                return conn
            except:
                pass
        # Last resort: try to decode the error message itself
        raise

if __name__ == '__main__':
    # Test the wrapper
    dsn = 'dbname=chronobrain user=postgres password=root host=localhost port=5432'
    print('Testing wrapper...')
    try:
        conn = get_connection_safe(dsn)
        print('✅ Connected!')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM documents')
        print(f'Documents: {c.fetchone()[0]}')
        conn.close()
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback
        traceback.print_exc()
