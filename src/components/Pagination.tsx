import './Pagination.css';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  onNextPage: () => void;
  onPrevPage: () => void;
}

const Pagination = ({ currentPage, totalPages, onNextPage, onPrevPage }: PaginationProps) => {
  return (
    <div className="pagination-controls">
      <button onClick={onPrevPage} disabled={currentPage === 1}>
        Previous
      </button>
      <span>Page {currentPage} of {totalPages}</span>
      <button onClick={onNextPage} disabled={currentPage === totalPages}>
        Next
      </button>
    </div>
  );
};

export default Pagination;