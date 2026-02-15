"""
__main__.py — Permite ejecutar Mikalia como módulo.

Esto hace posible ejecutar:
    python -m mikalia post --topic "Mi tema"

En vez de tener que especificar el archivo:
    python mikalia/cli.py post --topic "Mi tema"

¿Por qué? Porque Python busca __main__.py cuando ejecutas
un paquete con -m. Es la convención estándar.
"""

from mikalia.cli import main

if __name__ == "__main__":
    main()
