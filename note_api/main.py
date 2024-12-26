# -*- coding: utf-8 -*-
import os
import sys

from uuid import uuid4
from typing import List, Optional
from os import getenv
from typing_extensions import Annotated

from fastapi import Depends, FastAPI
from starlette.responses import RedirectResponse
from .backends import Backend, RedisBackend, MemoryBackend, GCSBackend
from .model import Note, CreateNoteRequest

from opentelemetry import trace
from opentelemetry.trace import get_tracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.gcp.trace import GCPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI()

if "pytest" not in sys.modules and os.getenv("ENV") != "test":
    # Set up OpenTelemetry tracer
    tracer_provider = TracerProvider()
    trace.set_tracer_provider(tracer_provider)

    # Configure GCP Trace exporter
    gcp_trace_exporter = GCPSpanExporter()
    span_processor = BatchSpanProcessor(gcp_trace_exporter)
    tracer_provider.add_span_processor(span_processor)

# Verify the FastAPI app is instrumented to automatically trace all requests
FastAPIInstrumentor.instrument_app(app)

my_backend: Optional[Backend] = None


def get_backend() -> Backend:
    global my_backend  # pylint: disable=global-statement
    if my_backend is None:
        backend_type = getenv('BACKEND', 'memory')
        print(backend_type)
        if backend_type == 'redis':
            my_backend = RedisBackend()
        elif backend_type == 'gcs':
            my_backend = GCSBackend()
        else:
            my_backend = MemoryBackend()
    return my_backend


@app.get('/')
def redirect_to_notes() -> None:
    return RedirectResponse(url='/notes')


@app.get('/notes')
def get_notes(backend: Annotated[Backend, Depends(get_backend)]) -> List[Note]:

    # Add custom span
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("get_notes_operation"):

        keys = backend.keys()

        Notes = []
        for key in keys:
            Notes.append(backend.get(key))
        return Notes


@app.get('/notes/{note_id}')
def get_note(note_id: str,
             backend: Annotated[Backend, Depends(get_backend)]) -> Note:
    return backend.get(note_id)


@app.put('/notes/{note_id}')
def update_note(note_id: str,
                request: CreateNoteRequest,
                backend: Annotated[Backend, Depends(get_backend)]) -> None:
    backend.set(note_id, request)


@app.post('/notes')
def create_note(request: CreateNoteRequest,
                backend: Annotated[Backend, Depends(get_backend)]) -> str:
    note_id = str(uuid4())
    backend.set(note_id, request)
    return note_id