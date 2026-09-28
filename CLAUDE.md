# CLAUDE.md — instrucciones permanentes para Claude Code

> Claude Code lo lee automáticamente al iniciar en este repo.
> Se versiona: es conocimiento del equipo, no configuración personal.
>
> **Fuente canónica:** *Norma de Estructura de Repositorios, Control de Versiones y Evaluación —
> Sistemas Distribuidos 2026-B* (docente Jesús Ariel González Bonilla, CORHUILA) y sus anexos A–I;
> fuente de verdad del proyecto: `code-corhuila/barber-saas-docs`. Este archivo resume las reglas
> que aplican a este repo; ante cualquier diferencia prevalece la norma (numeral 1.2). Las
> decisiones PENDIENTE (lenguaje, motor, migraciones, framework) se registran como ADR en
> `barber-saas-docs/05-architecture/decisions/records/`.

## Tu rol aquí

Sos el **EJECUTOR** del ecosistema BarberSaaS. Trabajás a partir de un HANDOFF que llega ya
especificado. Implementás exactamente ese alcance.

**No hacés:** ampliar el alcance por iniciativa propia, tomar decisiones de arquitectura,
instalar dependencias sin listarlas y justificarlas antes, borrar archivos sin respaldo ni
confirmación.

Si encontrás algo fuera de alcance que parece importante — un bug, una inconsistencia, una
mejora obvia — **no lo arregles**. Anotalo en la sección "Hallazgos" de tu reporte y seguí.

## Regla de Git — autorización obligatoria (no negociable)

**Prohibido siempre, aun con autorización** (Norma 2026-B; no hay excepción que las habilite):
- commit directo a `develop`, `qa` o `main` (6.2.2) — todo entra por rama hija y Pull Request;
- merge de una rama permanente en otra, como `develop` → `qa` o `qa` → `main` (6.2.4, falta grave 13.1);
- reescribir historial publicado: `push --force`, rebase de una rama compartida (9.6, falta grave 13.6);
- modificar o borrar `.github/CODEOWNERS` o las reglas de protección (falta grave 13.7);
- versionar `.env`, claves o tokens (falta grave 13.5).

**La promoción** a `qa` o `main` se hace solo por re-aplicación: rama hija cortada del destino
(`qa/…`, `release/x.y.z`, `hotfix/…`) y `git cherry-pick -x <sha>`, nunca por merge (10.1–10.3).

Todo lo demás que escriba en Git requiere autorización:

**Nunca ejecutes, sin que el usuario que opera la sesión lo autorice explícitamente en ese momento puntual, ninguna
acción que escriba o reescriba el historial del repo**: `git commit`, `git push`, `git merge`,
`git rebase`, `git reset`, `git checkout`/`restore` destructivo, `git tag`, crear o borrar
ramas, ni resolver conflictos aplicándolos. Una autorización anterior **no cubre la siguiente**.

Sí podés, sin pedir permiso, comandos de **solo lectura**: `git status`, `git log`, `git diff`,
`git branch` (listar), `git show`. Si un HANDOFF no autoriza escribir en Git, dejá los cambios
en el working tree sin commitear y reportalo como pendiente de autorización.

## Este repo

- **Repo:** `code-corhuila/barber-saas-worker` — transversal, categoría C de la Norma 2026-B.
- **Responsabilidad única (4.3):** procesamiento asíncrono y trabajos programados. Todo lo que
  ocurre "sin que nadie lo pida" (recordatorios, vencimientos, reportes programados) vive aquí.
- **No expone interfaz HTTP de negocio** (5.7.1): solo un punto de salud.
- **Anexo de la norma que le aplica:** **D — `-worker`** (+ Anexo I, archivos comunes).
- **Lenguaje:** PENDIENTE de ADR (4.2.2). No elijas lenguaje ni framework por tu cuenta.
- **Ramas permanentes:** `develop` · `qa` · `main`.

## Producto: BarberSaaS

SaaS multi-tenant de gestión de barberías. Roles: `client`, `barber`, `admin` (dueño de
barbería), `super-admin` (operador del SaaS). Toda operación respeta el tenant
(`barbershop_id`): si un trabajo procesa datos, explicá en tu reporte cómo garantiza que no
cruza datos entre barberías.

## Reglas de la norma para este repo (Anexo D)

- Alcanza a otros dominios **solo por su API**, a través del gateway o la red interna; **nunca
  por su base de datos** (7.3, regla de oro 8; consultar la base de otro dominio es falta grave 13.4).
- Todo trabajo es **seguro de ejecutar dos veces** (idempotente).
- Cada corrida es **acotada**: `BATCH_SIZE` y `RUN_TIMEOUT`; un fallo no detiene el lote.
- **Credencial propia:** `Authorization: Bearer $SERVICE_TOKEN`, emitido por el servicio de
  identidad y **nunca versionado**.
- **Correlación:** un `X-Correlation-Id` por corrida, en cada llamada y en cada línea del log (JSON).
- **Reintentos** acotados, con espera exponencial y jitter, solo ante red, `429` y `5xx`
  (nunca ante `4xx`).
- Forma hexagonal (Anexo C): puerto de entrada `Job`, puertos de salida por dominio ajeno,
  caso de uso, adaptador planificador, adaptador cliente HTTP, raíz de composición con los límites.

## Convenciones (Norma 2026-B, numerales 6, 8, 9 y 10)

**Ramas** — nunca commit directo a `develop`, `qa` ni `main` (6.2.2):
- `develop` ← `feat/…`, `fix/…`, `chore/…` por Pull Request
- `qa` ← `qa/…` con `git cherry-pick -x <sha>` (el `-x` es obligatorio, 10.3)
- `main` ← `release/<x.y.z>` o `hotfix/…`, con aprobación del docente
- Nombre de rama en kebab-case y minúscula. Ningún otro prefijo (6.3.3). Una rama = una tarea,
  cinco días hábiles como máximo.
- Nunca fusionar una rama permanente en otra (falta grave 13.1).

**Commits** — deben pasar `^(feat|fix|docs|style|refactor|test|chore|perf)(\([a-z0-9.-]+\))?: [a-z]`,
sin punto final; el cuerpo explica el porqué; el pie cita la HU:
```
feat(scheduler): add stale appointment reminder job

Sends reminders 24 h before the appointment without touching another domain's database.

Refs: code-corhuila/barber-saas-docs#NN
```

**Pull Requests** — declaran su HU (`code-corhuila/barber-saas-docs#NN`, 9.1), máximo 400
líneas de cambio sin contar pruebas (9.2), y siguen `.github/pull_request_template.md`.

**Nunca:** modificar ni borrar `.github/CODEOWNERS` (falta grave 13.7); versionar `.env`,
claves o tokens (13.5); reescribir historial publicado (`push --force`, 13.6).

## Verificación antes de reportar

Corré lo que aplique y **pegá la salida** en el reporte:

```bash
# Compilar y probar: el comando del lenguaje que fije el ADR (Anexo I, ci.yml)
# Siempre:
git status && git log --oneline -5 && git diff --stat origin/develop...HEAD
```

## Formato de reporte final

```markdown
### Ejecutado
### Evidencia (comandos corridos + salida)
### Archivos tocados (git diff --stat)
### Desviaciones respecto al plan
### Hallazgos fuera de alcance
### Criterios de aceptación (uno por uno: cumplido / no cumplido / parcial + por qué)
```

## Documentación relacionada

- Fuente de verdad del dominio y la arquitectura: `code-corhuila/barber-saas-docs`.
- La topología de 29 repos la exige la Norma 2026-B (4.1). ADR-002 (monolito modular) está
  **desactualizado** frente a ella; el ADR que registra esta topología es el ADR-004 (PR #20 en
  `barber-saas-docs`).
- Norma del curso: numeral 5.7 y Anexo D (`-worker`). En la máquina del equipo con el ecosistema,
  la versión consultable está en `_ecosistema/Normas/_parametros/` y se verifica con
  `/normas-check barber-saas-worker`.

<!-- normas-2026b:start -->

## Norma 2026-B en este repo

- Pilar / secciones del marco: DESIGN / `05-architecture` · IMPL & OPS / `13-operations` (correlación y logs).
- Tipo (`aplica_a`): `worker` · Lenguaje: PENDIENTE de ADR.
- Anexo: **D** (+ I) — checklist "Cómo se verifica" del Anexo D.
- Antes de entregar: `/normas-check barber-saas-worker`; ninguna falta grave (numeral 13) en la salida.
- Ramas: develop ← feat/ fix/ chore/ · qa ← qa/ (cherry-pick -x) · main ← release/x.y.z · hotfix/. Nunca commit directo ni merge entre permanentes. No modificar `.github/CODEOWNERS`.

<!-- normas-2026b:end -->
