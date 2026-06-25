import { useState, useCallback, useRef } from 'react';

export interface UndoRedoAction {
  type: string;
  undo: () => void;
  redo: () => void;
  label: string;
}

export function useUndoRedo() {
  const [undoStack, setUndoStack] = useState<UndoRedoAction[]>([]);
  const [redoStack, setRedoStack] = useState<UndoRedoAction[]>([]);
  const maxStack = useRef(50);

  const pushAction = useCallback((action: UndoRedoAction) => {
    setUndoStack(prev => {
      const next = [...prev, action];
      if (next.length > maxStack.current) next.shift();
      return next;
    });
    setRedoStack([]);
  }, []);

  const undo = useCallback(() => {
    const action = undoStack[undoStack.length - 1];
    if (!action) return;
    action.undo();
    setUndoStack(prev => prev.slice(0, -1));
    setRedoStack(prev => [...prev, action]);
  }, [undoStack]);

  const redo = useCallback(() => {
    const action = redoStack[redoStack.length - 1];
    if (!action) return;
    action.redo();
    setRedoStack(prev => prev.slice(0, -1));
    setUndoStack(prev => [...prev, action]);
  }, [redoStack]);

  return { undoStack, redoStack, pushAction, undo, redo, canUndo: undoStack.length > 0, canRedo: redoStack.length > 0 };
}
