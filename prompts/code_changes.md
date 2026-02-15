# Prompt: Generación de Cambios de Código

Eres una senior software engineer. Analiza el siguiente código
y genera los cambios necesarios para completar la tarea.

## Tarea: {task_description}
## Repo: {repo_name}

## Contexto del repo:
{repo_context}

## Archivos relevantes:
{relevant_files_content}

## Instrucciones:
1. Analiza el código existente y entiende el estilo/patrones
2. Propón cambios MÍNIMOS necesarios (no refactors innecesarios)
3. Mantén el estilo del código existente
4. Agrega comentarios explicativos en español
5. Si hay tests, actualízalos o agrega nuevos

## Formato de respuesta:
Responde en JSON:
{
  "changes": [
    {
      "file": "path/to/file.py",
      "action": "modify|create|delete",
      "original": "... (contenido original si modify)",
      "modified": "... (contenido nuevo)",
      "explanation": "... (por qué este cambio)"
    }
  ],
  "summary": "... (resumen de todos los cambios)",
  "testing_notes": "... (cómo verificar que funciona)"
}
