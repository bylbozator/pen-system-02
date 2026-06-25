import { comments as commentsApi } from '../api';
import type { IThreadComment, IBaseComment } from '@univerjs/thread-comment';
import type { IThreadCommentDataSource } from '@univerjs/thread-comment';
import type { IDocumentBody } from '@univerjs/core';

function textToBody(text: string): IDocumentBody {
  return { dataStream: text + '\r\n' };
}

function bodyToText(body: IDocumentBody): string {
  return body.dataStream.replace(/\r\n$/, '');
}

function mapBackendComment(c: any, datasetId: number): IThreadComment {
  return {
    id: String(c.id),
    threadId: c.thread_id || `${c.row_index ?? c.row_id}-${c.column_id}`,
    ref: c.ref || '',
    unitId: String(datasetId),
    subUnitId: c.sub_unit_id || 'main',
    personId: String(c.created_by),
    text: textToBody(c.comment),
    dT: c.created_at || new Date().toISOString(),
    updateT: c.updated_at || undefined,
    resolved: c.resolved || false,
    parentId: c.parent_id ? String(c.parent_id) : undefined,
  };
}

export function createCommentDataSource(datasetId: number): IThreadCommentDataSource {
  return {
    addComment: async (comment: IThreadComment): Promise<IThreadComment> => {
      const text = bodyToText(comment.text);
      const res = await commentsApi.create(datasetId, {
        comment: text,
        ref: comment.ref,
        thread_id: comment.threadId,
        row_index: (comment as any).row ?? null,
        col_index: (comment as any).column ?? null,
        sub_unit_id: comment.subUnitId,
        parent_id: comment.parentId ? parseInt(comment.parentId, 10) : null,
      });
      return mapBackendComment(res.data, datasetId);
    },

    updateComment: async (comment: IThreadComment): Promise<boolean> => {
      const text = bodyToText(comment.text);
      const res = await commentsApi.update(datasetId, parseInt(comment.id, 10), {
        comment: text,
      });
      return res.status === 200;
    },

    resolveComment: async (comment: IThreadComment): Promise<boolean> => {
      const res = await commentsApi.update(datasetId, parseInt(comment.id, 10), {
        resolved: !!comment.resolved,
      });
      return res.status === 200;
    },

    deleteComment: async (
      unitId: string,
      subUnitId: string,
      threadId: string,
      commentId: string,
    ): Promise<boolean> => {
      const res = await commentsApi.delete(datasetId, parseInt(commentId, 10));
      return res.status === 200;
    },

    listComments: async (
      unitId: string,
      subUnitId: string,
      threadIds: string[],
    ): Promise<IBaseComment[]> => {
      const res = await commentsApi.listAll(datasetId, subUnitId === 'main' ? undefined : subUnitId);
      const items = res.data as any[];
      if (!Array.isArray(items)) return [];
      return items.map((c) => mapBackendComment(c, datasetId));
    },

    saveCommentToSnapshot: (comment: IThreadComment) => ({
      id: comment.id,
      threadId: comment.threadId,
      ref: comment.ref,
    }),
  };
}
