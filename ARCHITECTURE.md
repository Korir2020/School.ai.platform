# School AI Platform — Architecture

## Main System

School
↓
Users & Permissions
↓
Students
↓
Teachers
↓
Classes & Streams
↓
Subjects
↓
Academic Years & Terms
↓
Exams
↓
Marks
↓
Grades
↓
Analytics
↓
Reports

## Core Technology

Backend: Django + Django REST Framework
Database: PostgreSQL
Frontend: React / Next.js
AI: Separate AI Service
Mobile: Offline-first Android/PWA architecture

## Core Principles

1. Security first
2. Offline-first design
3. AI must be explainable
4. AI must not silently change official records
5. Human confirmation for important actions
6. The core system must work without AI
7. Architecture must support future expansion
