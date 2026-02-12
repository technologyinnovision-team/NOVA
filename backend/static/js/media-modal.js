/**
 * Media Library Modal Controller
 * Handles media fetching, uploading, and selection for the media modal.
 */

const MediaLibrary = {
    modalId: 'media-library-modal',
    params: {
        page: 1,
        search: '',
        isLoading: false,
        hasNext: false,
        selectedFiles: [] // Array of file objects or URLs
    },
    config: {
        multiSelect: false,
        onSelect: null, // Callback function(selectedFiles)
    },

    init() {
        // Event listeners are bound when modal opens
        this._bindEvents();
    },

    open(config = {}) {
        this.config = { ...this.config, ...config };
        this.params.selectedFiles = [];
        this.params.page = 1;
        this.params.search = '';

        const modal = document.getElementById(this.modalId);
        if (modal) {
            modal.classList.remove('hidden');
            this.loadMedia(1, true);
        }
    },

    close() {
        const modal = document.getElementById(this.modalId);
        if (modal) {
            modal.classList.add('hidden');
        }
    },

    _bindEvents() {
        const modalInfo = document.getElementById('media-modal-close');
        if (modalInfo) modalInfo.addEventListener('click', () => this.close());

        const cancelBtn = document.getElementById('media-modal-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', () => this.close());

        const insertBtn = document.getElementById('media-modal-insert');
        if (insertBtn) insertBtn.addEventListener('click', () => this.handleInsert());

        const searchInput = document.getElementById('media-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.params.search = e.target.value;
                this.loadMedia(1, true); // Debounce could be added here
            });
        }

        const loadMoreBtn = document.getElementById('media-load-more');
        if (loadMoreBtn) loadMoreBtn.addEventListener('click', () => this.loadNextPage());

        // Tab Switching
        const tabUpload = document.getElementById('tab-upload-btn');
        const tabLibrary = document.getElementById('tab-library-btn');
        const viewUpload = document.getElementById('view-upload');
        const viewLibrary = document.getElementById('view-library');

        if (tabUpload && tabLibrary) {
            tabUpload.addEventListener('click', () => {
                tabUpload.classList.add('text-gold', 'border-b-2', 'border-gold');
                tabLibrary.classList.remove('text-gold', 'border-b-2', 'border-gold');
                viewUpload.classList.remove('hidden');
                viewLibrary.classList.add('hidden');
            });

            tabLibrary.addEventListener('click', () => {
                tabLibrary.classList.add('text-gold', 'border-b-2', 'border-gold');
                tabUpload.classList.remove('text-gold', 'border-b-2', 'border-gold');
                viewLibrary.classList.remove('hidden');
                viewUpload.classList.add('hidden');
                if (document.querySelector('#media-grid').children.length === 0) {
                    this.loadMedia(1, true);
                }
            });
        }

        // Upload Area
        const dropzone = document.getElementById('media-dropzone');
        const fileInput = document.getElementById('media-upload-input');

        if (dropzone && fileInput) {
            dropzone.addEventListener('click', () => fileInput.click());
            dropzone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropzone.classList.add('border-gold', 'bg-gold/5');
            });
            dropzone.addEventListener('dragleave', () => {
                dropzone.classList.remove('border-gold', 'bg-gold/5');
            });
            dropzone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropzone.classList.remove('border-gold', 'bg-gold/5');
                if (e.dataTransfer.files.length > 0) {
                    this.uploadFiles(e.dataTransfer.files);
                }
            });
            fileInput.addEventListener('change', (e) => {
                if (e.target.files.length > 0) {
                    this.uploadFiles(e.target.files);
                }
            });
        }
    },

    async loadMedia(page = 1, reset = false) {
        if (this.params.isLoading) return;
        this.params.isLoading = true;

        const grid = document.getElementById('media-grid');
        const loader = document.getElementById('media-loader');
        const loadMoreBtn = document.getElementById('media-load-more');

        if (reset) {
            grid.innerHTML = '';
            this.params.page = 1;
        }

        if (loader) loader.classList.remove('hidden');
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');

        try {
            const response = await fetch(`/admin/media/api/list?page=${page}&search=${encodeURIComponent(this.params.search)}`);
            const data = await response.json();

            this.params.hasNext = data.has_next;

            this.renderMedia(data.files);

            if (data.has_next && loadMoreBtn) {
                loadMoreBtn.classList.remove('hidden');
            }

        } catch (error) {
            console.error('Error loading media:', error);
            grid.innerHTML = '<div class="col-span-full text-center p-4 text-red-500">Error loading media.</div>';
        } finally {
            this.params.isLoading = false;
            if (loader) loader.classList.add('hidden');
        }
    },

    loadNextPage() {
        if (this.params.hasNext) {
            this.params.page++;
            this.loadMedia(this.params.page, false);
        }
    },

    renderMedia(files) {
        const grid = document.getElementById('media-grid');

        files.forEach(file => {
            const el = document.createElement('div');
            el.className = 'group relative aspect-square bg-gray-100 rounded-lg cursor-pointer overflow-hidden border border-gray-200 hover:border-gold transition-all';
            el.innerHTML = `
                <img src="${file.url}" class="w-full h-full object-cover">
                <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <span class="text-white text-xs font-medium">${file.name}</span>
                </div>
                <!-- Selection Checkmark -->
                <div class="absolute top-2 right-2 w-6 h-6 bg-gold text-white rounded-full flex items-center justify-center opacity-0 scale-0 transition-all select-indicator">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>
                </div>
            `;

            // Check if already selected (maintain state across paginations if desired, though simple usage resets on open)
            if (this.params.selectedFiles.some(f => f.url === file.url)) {
                el.querySelector('.select-indicator').classList.remove('opacity-0', 'scale-0');
                el.classList.add('ring-2', 'ring-gold');
            }

            el.addEventListener('click', () => this.toggleSelection(file, el));
            grid.appendChild(el);
        });
    },

    toggleSelection(file, element) {
        const indicator = element.querySelector('.select-indicator');

        if (this.config.multiSelect) {
            const index = this.params.selectedFiles.findIndex(f => f.url === file.url);
            if (index > -1) {
                this.params.selectedFiles.splice(index, 1);
                indicator.classList.add('opacity-0', 'scale-0');
                element.classList.remove('ring-2', 'ring-gold');
            } else {
                this.params.selectedFiles.push(file);
                indicator.classList.remove('opacity-0', 'scale-0');
                element.classList.add('ring-2', 'ring-gold');
            }
        } else {
            // Single select: clear others
            this.params.selectedFiles = [file];

            // UI Update
            const allItems = document.getElementById('media-grid').children;
            Array.from(allItems).forEach(item => {
                const ind = item.querySelector('.select-indicator');
                if (ind) ind.classList.add('opacity-0', 'scale-0');
                item.classList.remove('ring-2', 'ring-gold');
            });

            indicator.classList.remove('opacity-0', 'scale-0');
            element.classList.add('ring-2', 'ring-gold');
        }

        this.updateInsertButton();
    },

    updateInsertButton() {
        const btn = document.getElementById('media-modal-insert');
        if (btn) {
            const count = this.params.selectedFiles.length;
            btn.textContent = count > 0 ? `Insert Media (${count})` : 'Insert Media';
            btn.disabled = count === 0;
            if (count > 0) btn.classList.remove('opacity-50', 'cursor-not-allowed');
            else btn.classList.add('opacity-50', 'cursor-not-allowed');
        }
    },

    async uploadFiles(fileList) {
        const uploadStatus = document.getElementById('upload-status');
        if (uploadStatus) uploadStatus.classList.remove('hidden');

        let successCount = 0;

        for (let i = 0; i < fileList.length; i++) {
            const file = fileList[i];
            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/admin/media/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();

                if (data.success) {
                    successCount++;
                    // Automatically add to selection if single upload? 
                    // Or simply switch to library view and refresh
                }
            } catch (err) {
                console.error(err);
            }
        }

        if (uploadStatus) uploadStatus.classList.add('hidden');

        // Switch to library tab and refresh
        const tabLibrary = document.getElementById('tab-library-btn');
        if (tabLibrary) tabLibrary.click();
        this.loadMedia(1, true);
    },

    handleInsert() {
        if (this.config.onSelect) {
            this.config.onSelect(this.params.selectedFiles);
        }
        this.close();
    }
};

document.addEventListener('DOMContentLoaded', () => {
    MediaLibrary.init();
});
