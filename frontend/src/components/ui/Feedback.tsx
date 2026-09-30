type FeedbackProps = {
  type?: 'error' | 'success' | 'info';
  children: string;
};

const Feedback = ({ type = 'info', children }: FeedbackProps) => (
  <div className={`feedback feedback--${type}`} role={type === 'error' ? 'alert' : 'status'}>
    {children}
  </div>
);

export default Feedback;
